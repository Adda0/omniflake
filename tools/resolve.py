#!/usr/bin/env python3
"""Resolve harvested candidates into pinned, verified flake references.

For each repo this needs three things, all obtainable in one GraphQL round
trip per batch: the default branch commit (to pin a rev), whether a root
flake.nix exists (to reject non-flakes), and flake.lock (whose root node
lists the flake's declared input names, which is what `follows` needs).

This is incremental. resolved.jsonl is a database that is kept and added
to, not regenerated: pass --known to skip repos already in it, and
--refresh to additionally re-pin the ones already known.

Attribute names are sticky, which matters because they are API. A name
already assigned in the known set keeps its owner forever, so a repo that
later gains stars cannot take a bare name out from under a consumer that
already writes omniflake.flakes.<name>.

Output: JSON lines of {name, owner, repo, rev, inputs, stars}.
"""

import argparse, json, os, subprocess, sys, time, collections
import urllib.error, urllib.parse, urllib.request

BATCH = 40
# Skip absurd locks; they are almost always vendored monorepos.
MAX_LOCK_BYTES = 2_000_000

QUERY_HEAD = "query {"
QUERY_TAIL = "}"


def repo_fragment(alias, owner, repo):
    """One aliased repository selection: HEAD oid, flake.nix, flake.lock."""
    return f"""
  {alias}: repository(owner: "{owner}", name: "{repo}") {{
    defaultBranchRef {{ target {{ oid }} }}
    flakeNix: object(expression: "HEAD:flake.nix") {{ __typename }}
    flakeLock: object(expression: "HEAD:flake.lock") {{
      ... on Blob {{ text byteSize }}
    }}
  }}"""


def read_token():
    """Read the GitHub token once, in-process.

    Every `gh` invocation asks the system keyring to unlock, so shelling out
    per batch means one prompt per batch. Read it once instead.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=60
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


TOKEN = read_token()


def run_batch(batch):
    """Issue one GraphQL query for up to BATCH repos; return the data map."""
    parts = [repo_fragment(f"r{i}", b["owner"], b["repo"]) for i, b in enumerate(batch)]
    query = QUERY_HEAD + "\n".join(parts) + QUERY_TAIL
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                return (json.loads(fh.read().decode()) or {}).get("data") or {}
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 502):
                time.sleep(10 * (attempt + 1))
                continue
            return {}
        except Exception:
            time.sleep(3)
    return {}


def sanitize(repo):
    """GitHub repo name -> a legal, readable Nix attribute name."""
    name = repo.lower()
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)
    # A Nix identifier may not start with a digit or dash.
    if not out or not out[0].isalpha():
        out = "f-" + out
    return out


def load_known(path):
    """Read an existing resolved.jsonl into (by_repo, taken_names)."""
    by_repo, taken = {}, {}
    if not path:
        return by_repo, taken
    try:
        fh = open(path)
    except FileNotFoundError:
        return by_repo, taken
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            e = json.loads(line)
            by_repo[(e["owner"], e["repo"])] = e
            # Remember which repo owns each name so it stays put.
            taken[e["name"]] = (e["owner"], e["repo"])
    return by_repo, taken


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--known", help="existing resolved.jsonl to extend")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="also re-pin repos already present in --known",
    )
    args = ap.parse_args()

    known, taken = load_known(args.known)

    cands = [json.loads(l) for l in sys.stdin if l.strip() and not l.startswith("#")]
    # Highest-starred first, so the better-known flake wins any *new* name clash.
    cands.sort(key=lambda c: -c.get("stars", 0))

    # Re-emit everything already known, so stdout is always the full database.
    skipped = 0
    if not args.refresh:
        for entry in known.values():
            print(json.dumps(entry), flush=True)
        cands = [c for c in cands if (c["owner"], c["repo"]) not in known]
        skipped = len(known)
        print(
            f"# carried over {skipped} known, resolving {len(cands)} new",
            file=sys.stderr,
            flush=True,
        )

    used = collections.Counter()
    emitted = 0

    for i in range(0, len(cands), BATCH):
        batch = cands[i : i + BATCH]
        data = run_batch(batch)
        for j, cand in enumerate(batch):
            node = data.get(f"r{j}")
            if not node:
                continue
            # Must be a real flake with a resolvable commit.
            if not node.get("flakeNix"):
                continue
            ref = (node.get("defaultBranchRef") or {}).get("target") or {}
            rev = ref.get("oid")
            if not rev:
                continue

            # The lock's root node names the flake's declared direct inputs.
            inputs = []
            lock = node.get("flakeLock") or {}
            text = lock.get("text")
            if text and (lock.get("byteSize") or 0) <= MAX_LOCK_BYTES:
                try:
                    parsed = json.loads(text)
                    inputs = sorted(
                        (
                            parsed.get("nodes", {}).get("root", {}).get("inputs", {})
                        ).keys()
                    )
                except Exception:
                    inputs = []

            # Names are sticky: a repo keeps the name it was first given, and
            # never takes one another repo already holds.
            prior = known.get((cand["owner"], cand["repo"]))
            if prior:
                name = prior["name"]
            else:
                base = sanitize(cand["repo"])
                owner_qualified = f"{base}-{sanitize(cand['owner'])}"
                holder = taken.get(base)
                if holder in (None, (cand["owner"], cand["repo"])) and used[base] == 0:
                    name = base
                else:
                    name = owner_qualified
                used[base] += 1
                taken[name] = (cand["owner"], cand["repo"])

            print(
                json.dumps(
                    {
                        "name": name,
                        "owner": cand["owner"],
                        "repo": cand["repo"],
                        "rev": rev,
                        "inputs": inputs,
                        "stars": cand.get("stars", 0),
                    }
                ),
                flush=True,
            )
            emitted += 1
        print(f"# resolved {emitted}/{i + len(batch)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
