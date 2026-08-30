#!/usr/bin/env python3
"""Build site-data.json, the one file the site's index page loads.

Joins index.json (what is indexed, at which revision) with resolved.jsonl
(owner, repo, stars, description) and failures.jsonl (what could not be
pinned, and why), so the page can answer "is X in here and under what
name" and show the health of the index without evaluating anything.
"""

import argparse, json, os, time


def read_jsonl(path):
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--blocklist", default="blocklist.txt")
    ap.add_argument("--locks", default="locks")
    ap.add_argument("--out", default="site-data.json")
    args = ap.parse_args()

    index = json.load(open(args.index))
    by_name = {r["name"]: r for r in read_jsonl(args.resolved)}
    blocked = set()
    if os.path.exists(args.blocklist):
        blocked = {
            l.strip()
            for l in open(args.blocklist)
            if l.strip() and not l.startswith("#")
        }

    flakes = []
    for name, entry in sorted(index.items()):
        locked = entry["locked"]
        row = by_name.get(name, {})

        # The size of the input graph: from the committed lock as resolve.py
        # saw it, or from the stored lock when that is what the loader uses.
        lock_nodes = row.get("lock_nodes")
        if entry.get("lock"):
            key = locked.get("rev") or locked["narHash"].replace("/", "_").replace(
                "=", ""
            )
            path = os.path.join(args.locks, f"{key}.json")
            if os.path.exists(path):
                lock_nodes = max(len(json.load(open(path)).get("nodes", {})) - 1, 0)

        flakes.append(
            {
                "name": name,
                "owner": locked.get("owner") or row.get("owner", ""),
                "repo": locked.get("repo") or row.get("repo", ""),
                "type": locked.get("type", ""),
                "rev": locked.get("rev", ""),
                "lastModified": locked.get("lastModified", 0),
                "checkedAt": row.get("resolved_at", 0),
                "stars": row.get("stars", 0),
                "description": row.get("description", ""),
                "inputs": row.get("inputs", []),
                "lockNodes": lock_nodes,
                "storedLock": bool(entry.get("lock")),
            }
        )

    failures = []
    for f in read_jsonl(args.failures):
        if f["name"] in blocked:
            continue
        # The last line of Nix's trace is the one that says what went wrong.
        error = [l for l in f["error"].splitlines() if l.strip()]
        failures.append(
            {
                "name": f["name"],
                "ref": f["ref"],
                "error": error[-1].strip() if error else "",
                "stars": by_name.get(f["name"], {}).get("stars", 0),
            }
        )
    failures.sort(key=lambda f: (-f["stars"], f["name"]))

    data = {
        "generated": int(time.time()),
        "count": len(flakes),
        "storedLocks": sum(1 for f in flakes if f["storedLock"]),
        "flakes": flakes,
        "failures": failures,
    }
    with open(args.out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(f"site-data: {len(flakes)} flakes, {len(failures)} failures")


if __name__ == "__main__":
    main()
