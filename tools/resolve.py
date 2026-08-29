#!/usr/bin/env python3
"""Resolve harvested candidates into pinned, verified flake references.

For each repo this needs three things, all obtainable in one GraphQL round
trip per batch: the default branch commit (to pin a rev), whether a root
flake.nix exists (to reject non-flakes), and flake.lock (whose root node
lists the flake's declared input names, which is what `follows` needs).

Output: JSON lines of {name, owner, repo, rev, inputs, stars}.
"""
import json, subprocess, sys, collections

BATCH = 40
# Skip absurd locks; they are almost always vendored monorepos.
MAX_LOCK_BYTES = 2_000_000

QUERY_HEAD = "query {"
QUERY_TAIL = "}"


def repo_fragment(alias, owner, repo):
    """One aliased repository selection: HEAD oid, flake.nix, flake.lock."""
    return f'''
  {alias}: repository(owner: "{owner}", name: "{repo}") {{
    defaultBranchRef {{ target {{ oid }} }}
    flakeNix: object(expression: "HEAD:flake.nix") {{ __typename }}
    flakeLock: object(expression: "HEAD:flake.lock") {{
      ... on Blob {{ text byteSize }}
    }}
  }}'''


def run_batch(batch):
    """Issue one GraphQL query for up to BATCH repos; return the data map."""
    parts = [repo_fragment(f"r{i}", b["owner"], b["repo"]) for i, b in enumerate(batch)]
    query = QUERY_HEAD + "\n".join(parts) + QUERY_TAIL
    try:
        out = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            return {}
        return (json.loads(out.stdout) or {}).get("data") or {}
    except Exception:
        return {}


def sanitize(repo):
    """GitHub repo name -> a legal, readable Nix attribute name."""
    name = repo.lower()
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name)
    # A Nix identifier may not start with a digit or dash.
    if not out or not out[0].isalpha():
        out = "f-" + out
    return out


def main():
    cands = [json.loads(l) for l in sys.stdin if l.strip() and not l.startswith("#")]
    # Highest-starred first, so the better-known flake wins any name clash.
    cands.sort(key=lambda c: -c.get("stars", 0))

    used = collections.Counter()
    emitted = 0

    for i in range(0, len(cands), BATCH):
        batch = cands[i:i + BATCH]
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
                    inputs = sorted((parsed.get("nodes", {})
                                     .get("root", {})
                                     .get("inputs", {})).keys())
                except Exception:
                    inputs = []

            # Disambiguate attribute names across different owners.
            base = sanitize(cand["repo"])
            used[base] += 1
            name = base if used[base] == 1 else f"{base}-{sanitize(cand['owner'])}"

            print(json.dumps({
                "name": name,
                "owner": cand["owner"],
                "repo": cand["repo"],
                "rev": rev,
                "inputs": inputs,
                "stars": cand.get("stars", 0),
            }), flush=True)
            emitted += 1
        print(f"# resolved {emitted}/{i + len(batch)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
