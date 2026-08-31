#!/usr/bin/env python3
"""Resolve harvested candidates into pinned, verified flake references.

For each repo this needs three things, all obtainable in one GraphQL round
trip per batch: the default branch commit (to pin a rev), whether a root
flake.nix exists (to reject non-flakes), and flake.lock (whose root node
lists the flake's declared input names, which is what `follows` needs).

This is incremental. resolved.jsonl is a database that is kept and added
to, not regenerated: pass --known to skip repos already in it, and
--refresh to additionally re-pin the ones already known. Rows that were
resolved outside the GitHub API (tools/manual.py writes them) come in via
--merge and win over any other row for the same repository.

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
        help="re-resolve every repo already present in --known",
    )
    ap.add_argument(
        "--refresh-oldest",
        type=int,
        default=0,
        metavar="N",
        help="re-resolve the N known repos resolved longest ago",
    )
    ap.add_argument(
        "--merge",
        metavar="FILE",
        help="externally resolved rows to fold in; they win over known rows",
    )
    args = ap.parse_args()

    known, taken = load_known(args.known)

    # Externally resolved rows (tools/manual.py) are authoritative for their
    # repository: the known row, a refresh, and any harvested candidate for
    # the same repo all yield to them. Their names join the taken set so a
    # new candidate cannot claim a name a merged row already uses, but a
    # name some known repo already holds stays with that repo.
    merged, merged_names = load_known(args.merge)
    for name, repo_key in merged_names.items():
        taken.setdefault(name, repo_key)

    cands = [json.loads(l) for l in sys.stdin if l.strip() and not l.startswith("#")]
    # Highest-starred first, so the better-known flake wins any *new* name clash.
    cands.sort(key=lambda c: -c.get("stars", 0))
    cands = [
        c
        for c in cands
        if (c["owner"], c["repo"]) not in known
        and (c["owner"], c["repo"]) not in merged
    ]

    # Known rows to look at again: all of them, or the ones resolved longest
    # ago. A rolling refresh keeps each run's work bounded while every row
    # comes round on a fixed cadence.
    if args.refresh:
        refresh = list(known.values())
    else:
        by_age = sorted(known.values(), key=lambda r: r.get("resolved_at", 0))
        refresh = by_age[: args.refresh_oldest]
    refresh = [r for r in refresh if (r["owner"], r["repo"]) not in merged]
    refresh_keys = {(r["owner"], r["repo"]) for r in refresh}

    # Re-emit what is not being refreshed, so stdout is always the full
    # database.
    for entry in known.values():
        key = (entry["owner"], entry["repo"])
        if key in refresh_keys or key in merged:
            continue
        print(json.dumps(entry), flush=True)
    print(
        f"# carried over {len(known) - len(refresh)} known, "
        f"refreshing {len(refresh)}, resolving {len(cands)} new",
        file=sys.stderr,
        flush=True,
    )

    # Refreshed rows are candidates like any other, resolved after the new
    # ones so a new repo's name is decided first by stars as before.
    cands += [
        {"owner": r["owner"], "repo": r["repo"], "stars": r.get("stars", 0)}
        for r in refresh
    ]

    now = int(time.time())
    used = collections.Counter()
    emitted = 0

    for i in range(0, len(cands), BATCH):
        batch = cands[i : i + BATCH]
        data = run_batch(batch)
        for j, cand in enumerate(batch):
            prior = known.get((cand["owner"], cand["repo"]))
            node = data.get(f"r{j}")
            ref = ((node or {}).get("defaultBranchRef") or {}).get("target") or {}
            rev = ref.get("oid")

            # Must be a real flake with a resolvable commit. A known row that
            # fails now, whether the repo is gone or GitHub did not answer,
            # is kept as it was: dropping it would release its name.
            if not node or not node.get("flakeNix") or not rev:
                if prior:
                    print(json.dumps(prior), flush=True)
                continue

            # The lock's root node names the flake's declared direct inputs,
            # and its node count is the size of the transitive graph.
            inputs = []
            lock_nodes = None
            lock = node.get("flakeLock") or {}
            text = lock.get("text")
            if text and (lock.get("byteSize") or 0) <= MAX_LOCK_BYTES:
                try:
                    parsed = json.loads(text)
                    nodes = parsed.get("nodes", {})
                    inputs = sorted((nodes.get("root", {}).get("inputs", {})).keys())
                    lock_nodes = max(len(nodes) - 1, 0)
                except Exception:
                    inputs = []

            # Names are sticky: a repo keeps the name it was first given, and
            # never takes one another repo already holds.
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

            row = {
                "name": name,
                "owner": cand["owner"],
                "repo": cand["repo"],
                "rev": rev,
                "inputs": inputs,
                "stars": cand.get("stars", 0),
                "resolved_at": now,
            }
            if lock_nodes is not None:
                row["lock_nodes"] = lock_nodes
            # Fields other tools fill in survive a refresh.
            if prior and "description" in prior:
                row["description"] = prior["description"]
            print(json.dumps(row), flush=True)
            emitted += 1
        print(f"# resolved {emitted}/{i + len(batch)}", file=sys.stderr, flush=True)

    # The externally resolved rows themselves, emitted last so the file
    # reads in the same order the old append-then-dedup produced.
    for entry in merged.values():
        print(json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()
