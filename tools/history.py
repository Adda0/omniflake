#!/usr/bin/env python3
"""Append one row a day to history.jsonl: what the index looked like today.

Everything the site shows is otherwise a snapshot, so it can say how many
flakes are indexed but not whether that is more than last month. This
records the aggregates a trend needs, one line per day.

It stays in the flake tree, unlike the databases it reads. At 243 bytes a
row that is 87 KiB a year, it appends rather than rewrites so it costs
almost nothing in history, and being committed is what makes it auditable
in the same diff as the index it describes.

The counts that come from the pipeline's own working files -- the library
and personal tiers, the candidate pool -- are recorded here because this is
the only moment they exist: classify.py derives them on every run and
nothing commits them.

Re-running on the same day replaces that day's row rather than adding a
second, so a re-run after a failure does not double-count.
"""

import argparse, json, os, statistics, time

DAY_SECONDS = 86400


def read_jsonl(path):
    if not path or not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                yield json.loads(line)


def count_lines(path):
    """Rows in a jsonl file, or None when the file is not there.

    None rather than 0: a run invoked with --no-harvest never writes
    library.jsonl, and a zero would read as "the tier emptied out".
    """
    if not path or not os.path.exists(path):
        return None
    return sum(1 for _ in read_jsonl(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--pins", default="pins.jsonl")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--library", default="library.jsonl")
    ap.add_argument("--personal", default="personal.jsonl")
    ap.add_argument("--candidates", default="candidates.jsonl")
    ap.add_argument("--out", default="history.jsonl")
    ap.add_argument("--date", help="the row's date, YYYY-MM-DD (default: today, UTC)")
    args = ap.parse_args()

    index = json.load(open(args.index))
    pins = {p["name"]: p for p in read_jsonl(args.pins)}
    resolved = {r["name"]: r for r in read_jsonl(args.resolved)}

    now = int(time.time())
    date = args.date or time.strftime("%Y-%m-%d", time.gmtime(now))

    # The graph size the loader would walk for every indexed flake, from the
    # pin, falling back to what resolve.py counted off the committed lock.
    nodes = []
    for name in index:
        n = pins.get(name, {}).get("lock_nodes")
        if n is None:
            n = resolved.get(name, {}).get("lock_nodes")
        if n is not None:
            nodes.append(n)

    ages = [
        (now - e["locked"]["lastModified"]) / DAY_SECONDS
        for e in index.values()
        if e["locked"].get("lastModified")
    ]

    failures = list(read_jsonl(args.failures))

    row = {
        "date": date,
        "count": len(index),
        "storedLocks": sum(1 for e in index.values() if e.get("lock")),
        "failures": sum(1 for f in failures if not f.get("transient")),
        "pending": sum(1 for f in failures if f.get("transient")),
        "stars": sum(resolved.get(n, {}).get("stars", 0) for n in index),
    }
    if nodes:
        row["lockNodeSum"] = sum(nodes)
        row["lockNodeMedian"] = int(statistics.median(nodes))
    if ages:
        row["medianAgeDays"] = int(statistics.median(ages))
        row["freshMonth"] = sum(1 for a in ages if a < 30)
        row["freshYear"] = sum(1 for a in ages if a < 365)
    for key, path in (
        ("library", args.library),
        ("personal", args.personal),
        ("candidates", args.candidates),
    ):
        n = count_lines(path)
        if n is not None:
            row[key] = n

    rows = [r for r in read_jsonl(args.out) if r.get("date") != date]
    rows.append(row)
    rows.sort(key=lambda r: r["date"])

    tmp = args.out + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    os.replace(tmp, args.out)
    print(f"history: {len(rows)} rows, today is {json.dumps(row, sort_keys=True)}")


if __name__ == "__main__":
    main()
