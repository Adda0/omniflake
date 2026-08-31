#!/usr/bin/env python3
"""Build site-data.json, the one file the site's index page loads.

Joins index.json (what is indexed, at which revision) with resolved.jsonl
(owner, repo, stars, description) and failures.jsonl (what could not be
pinned, and why), so the page can answer "is X in here and under what
name" and show the health of the index without evaluating anything.
"""

import argparse, collections, json, os, statistics, time

DAY_SECONDS = 86400
# How many rows each leaderboard carries into the page. Enough to be worth
# reading, small enough that the whole stats block stays a rounding error
# next to the 12,000 flake rows beside it.
TOP_INPUTS = 100
TOP_HEAVIEST = 100
# The inputs `flakes.<name>` substitutes, mirrored from flake.nix. Counting
# how far one `follows` line reaches is the whole argument for the index.
FOUNDATIONS = ("nixpkgs", "flake-utils", "systems", "flake-parts", "flake-compat")

# One nixpkgs source tree, as the closure size Nix reports for the revision
# this flake pins:
#
#     nix path-info -S .#inputs.nixpkgs  ->  203 MB
#
# Trees differ a little between revisions; this is the order of magnitude,
# and it is what turns "3,254 distinct revisions" into a number anyone can
# feel. Re-measure if it ever looks wrong.
NIXPKGS_TREE_BYTES = 203 * 1024 * 1024


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


def build_stats(flakes, pins, now):
    """The aggregates the stats view draws, computed once at build time.

    Everything here is derivable from the rows already in this file, but
    deriving it in the browser means shipping the derivation and paying it
    on every page load, for numbers that change once a day.
    """
    # What the index's flakes declare, and how far one `follows` reaches.
    inputs = collections.Counter()
    foundation_edges = 0
    with_foundation = 0
    for f in flakes:
        names = f["inputs"]
        inputs.update(names)
        hits = sum(1 for i in names if i in FOUNDATIONS)
        foundation_edges += hits
        if hits:
            with_foundation += 1

    nodes = [f["lockNodes"] for f in flakes if f["lockNodes"] is not None]
    heaviest = sorted(
        ((f["lockNodes"], f["name"]) for f in flakes if f["lockNodes"]),
        reverse=True,
    )[:TOP_HEAVIEST]

    # When each flake's pinned revision was authored, and how stale that is.
    by_year = collections.Counter()
    ages = []
    for f in flakes:
        lm = f["lastModified"]
        if not lm:
            continue
        by_year[time.gmtime(lm).tm_year] += 1
        ages.append((now - lm) / DAY_SECONDS)

    stars = sorted((f["stars"] for f in flakes), reverse=True)
    total_stars = sum(stars)

    # Whether attention tracks maintenance: the share of each population
    # whose pinned revision is under a year old.
    def fresh_share(pred):
        pop = [f for f in flakes if pred(f) and f["lastModified"]]
        if not pop:
            return None
        fresh = sum(1 for f in pop if (now - f["lastModified"]) / DAY_SECONDS < 365)
        return round(100 * fresh / len(pop))

    # The input graph below the surface, from the summary pin.py records.
    lock_types = collections.Counter()
    nixpkgs_revs = collections.Counter()
    nixpkgs_dates = []
    for p in pins.values():
        lock_types.update(p.get("lock_types", {}))
        npk = p.get("lock_nixpkgs")
        if npk and npk.get("rev"):
            nixpkgs_revs[npk["rev"]] += 1
            if npk.get("lastModified"):
                nixpkgs_dates.append(npk["lastModified"])

    stats = {
        "distinctInputs": len(inputs),
        "inputs": inputs.most_common(TOP_INPUTS),
        "withFoundation": with_foundation,
        "foundationEdges": foundation_edges,
        "byYear": sorted(by_year.items()),
        "heaviest": [[name, n] for n, name in heaviest],
        "stars": {
            "total": total_stars,
            "zero": sum(1 for s in stars if s == 0),
            "ge100": sum(1 for s in stars if s >= 100),
            "ge1000": sum(1 for s in stars if s >= 1000),
            "top10Share": (
                round(100 * sum(stars[:10]) / total_stars) if total_stars else 0
            ),
            "freshSharePopular": fresh_share(lambda f: f["stars"] >= 100),
            "freshShareZero": fresh_share(lambda f: f["stars"] == 0),
        },
    }
    if nodes:
        stats["lockNodes"] = {
            "sum": sum(nodes),
            "median": int(statistics.median(nodes)),
            "counted": len(nodes),
        }
    if ages:
        stats["freshness"] = {
            "medianAgeDays": int(statistics.median(ages)),
            "d30": sum(1 for a in ages if a < 30),
            "d90": sum(1 for a in ages if a < 90),
            "d365": sum(1 for a in ages if a < 365),
        }
    if lock_types:
        stats["lockTypes"] = lock_types.most_common()
        stats["summarized"] = sum(1 for p in pins.values() if "lock_types" in p)
    if nixpkgs_revs:
        distinct = len(nixpkgs_revs)
        stats["nixpkgs"] = {
            "pins": sum(nixpkgs_revs.values()),
            "distinct": distinct,
            # What those revisions would cost if they were fetched rather
            # than followed. Nix already collapses equal revisions, so the
            # count that matters is the distinct one, not the pin count.
            "treeBytes": NIXPKGS_TREE_BYTES,
            "wasteBytes": distinct * NIXPKGS_TREE_BYTES,
            "medianLastModified": (
                int(statistics.median(nixpkgs_dates)) if nixpkgs_dates else None
            ),
            "oldestLastModified": min(nixpkgs_dates) if nixpkgs_dates else None,
        }
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="index.json")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument("--failures", default="failures.jsonl")
    ap.add_argument("--blocklist", default="blocklist.txt")
    ap.add_argument("--pins", default="pins.jsonl")
    ap.add_argument("--history", default="history.jsonl")
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

    now = int(time.time())
    data = {
        "generated": now,
        "count": len(flakes),
        "storedLocks": sum(1 for f in flakes if f["storedLock"]),
        "pending": pending,
        "flakes": flakes,
        "failures": failures,
        "stats": build_stats(flakes, pins, now),
        # One row a day. The trend charts have nothing to draw until this
        # has a few in it, which is why it starts being written now.
        "history": list(read_jsonl(args.history)),
    }
    with open(args.out, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    print(
        f"site-data: {len(flakes)} flakes, {len(failures)} failures, {pending} pending retry"
    )


if __name__ == "__main__":
    main()
