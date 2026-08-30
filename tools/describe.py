#!/usr/bin/env python3
"""Fill in fields resolve.py records but older rows of resolved.jsonl lack.

Two of them: the repository description, which is what makes the site
searchable by what a flake does rather than what it is called, and the
node count of the flake's lock at its pinned revision. Both come from one
GraphQL round trip per 40 repositories. Rows that already have the fields
are skipped, so update.sh can run this every time.

Rewrites resolved.jsonl in place. Rows are never removed or renamed here.
"""

import argparse, json, os, sys, time
import urllib.error, urllib.request

from resolve import BATCH, read_token

TOKEN = read_token()


# Skip absurd locks; they are almost always vendored monorepos.
MAX_LOCK_BYTES = 2_000_000


def query(batch):
    parts = [
        f'r{i}: repository(owner: {json.dumps(r["owner"])}, name: {json.dumps(r["repo"])}) {{ '
        f"description "
        f'flakeLock: object(expression: {json.dumps(r["rev"] + ":flake.lock")}) {{ ... on Blob {{ text byteSize }} }} '
        f"}}"
        for i, r in enumerate(batch)
    ]
    body = json.dumps({"query": "query {" + "\n".join(parts) + "}"}).encode()
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resolved", default="resolved.jsonl")
    args = ap.parse_args()

    rows = []
    with open(args.resolved) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                rows.append(json.loads(line))

    todo = [r for r in rows if "description" not in r or "lock_nodes" not in r]
    print(f"# {len(rows)} rows, {len(todo)} missing a field", file=sys.stderr)

    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        data = query(batch)
        for j, row in enumerate(batch):
            node = data.get(f"r{j}") or {}
            # An empty string records that GitHub had nothing, so the row is
            # not asked about again next run.
            if "description" not in row:
                row["description"] = (node.get("description") or "").strip()
            # A flake without a lock, or with one too large to read, gets 0:
            # the loader sees no graph in that case either.
            if "lock_nodes" not in row:
                lock = node.get("flakeLock") or {}
                text = lock.get("text")
                count = 0
                if text and (lock.get("byteSize") or 0) <= MAX_LOCK_BYTES:
                    try:
                        count = max(len(json.loads(text).get("nodes", {})) - 1, 0)
                    except Exception:
                        count = 0
                row["lock_nodes"] = count
        print(
            f"# described {min(i + BATCH, len(todo))}/{len(todo)}",
            file=sys.stderr,
            flush=True,
        )

    tmp = args.resolved + ".tmp"
    with open(tmp, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    os.replace(tmp, args.resolved)


if __name__ == "__main__":
    main()
