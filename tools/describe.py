#!/usr/bin/env python3
"""Fill in a one-line description for every flake in resolved.jsonl.

The description is what makes the site searchable by what a flake *does*
rather than what it is called, and GitHub hands it out for free in the same
GraphQL round trip resolve.py already makes. This script backfills rows
that predate the field and is otherwise a no-op, so update.sh can run it
every time.

Rewrites resolved.jsonl in place, adding "description" (possibly "") to
each row. Rows are never removed or renamed here.
"""

import argparse, json, os, sys, time
import urllib.error, urllib.request

from resolve import BATCH, read_token

TOKEN = read_token()


def query(batch):
    parts = [
        f'r{i}: repository(owner: {json.dumps(r["owner"])}, name: {json.dumps(r["repo"])}) {{ description }}'
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

    todo = [r for r in rows if "description" not in r]
    print(f"# {len(rows)} rows, {len(todo)} without a description", file=sys.stderr)

    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        data = query(batch)
        for j, row in enumerate(batch):
            node = data.get(f"r{j}") or {}
            # An empty string records that GitHub had nothing, so the row is
            # not asked about again next run.
            row["description"] = (node.get("description") or "").strip()
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
