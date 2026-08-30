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


def error_message(text):
    """The line of a Nix error that says what went wrong.

    Nix prints a trace of "… while" lines, then the message as the last
    "error: ..." line, then for a parse error an excerpt of the source, so
    the last line of the output is often a line of someone's flake.nix.
    The message is the last "error:" line with content; a following
    "at file:line" line is kept, since it says where.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    message = ""
    for i, line in enumerate(lines):
        if line.startswith("error:") and len(line) > len("error:"):
            message = line[len("error:") :].strip()
            if i + 1 < len(lines) and lines[i + 1].startswith("at "):
                message += " " + lines[i + 1].rstrip(":")
    if not message and lines:
        message = lines[-1]
    return message


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--blocklist", default="blocklist.txt")
    ap.add_argument("--pins", default="pins.jsonl")
    ap.add_argument("--out", default="site-data.json")
    args = ap.parse_args()

    index = json.load(open(args.index))
    by_name = {r["name"]: r for r in read_jsonl(args.resolved)}
    pins = {p["name"]: p for p in read_jsonl(args.pins)}
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

        # The size of the input graph, as pin.py saw the lock the loader
        # uses; the committed lock's count from resolve.py stands in for a
        # pin recorded before pin.py kept it.
        lock_nodes = pins.get(name, {}).get("lock_nodes", row.get("lock_nodes"))

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

    # A transient failure (GitHub's quota, a gateway error) says nothing
    # about the flake and is retried by the next run, so it is counted but
    # not listed as unpinnable.
    failures = []
    pending = 0
    for f in read_jsonl(args.failures):
        if f["name"] in blocked:
            continue
        if f.get("transient"):
            pending += 1
            continue
        failures.append(
            {
                "name": f["name"],
                "ref": f["ref"],
                "error": error_message(f["error"]),
                "stars": by_name.get(f["name"], {}).get("stars", 0),
            }
        )
    failures.sort(key=lambda f: (-f["stars"], f["name"]))

    data = {
        "generated": int(time.time()),
        "count": len(flakes),
        "storedLocks": sum(1 for f in flakes if f["storedLock"]),
        "pending": pending,
        "flakes": flakes,
        "failures": failures,
    }
    with open(args.out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(
        f"site-data: {len(flakes)} flakes, {len(failures)} failures, {pending} pending retry"
    )


if __name__ == "__main__":
    main()
