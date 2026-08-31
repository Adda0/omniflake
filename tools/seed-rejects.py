#!/usr/bin/env python3
"""Build the reject ledger from the databases that already exist.

resolve.py records a repository it checked and could not use, so that the
next run does not ask about it again. With an empty ledger the first run
after that lands re-queries everything it has ever rejected — 8,357
repositories, about 17 minutes — and, worse, every one of those rows then
falls due on the same future day, turning one run a week into a 17-minute
one.

The set is already derivable: candidates.jsonl minus resolved.jsonl is
exactly the repositories that were checked and are not in the database.
Seeding from it costs the first run nothing, and backdating each row by a
hash of owner/repo spreads the re-checks evenly from day one.

    tools/seed-rejects.py > rejects.jsonl

This is a one-off. Keep it as a repair tool for a ledger that has drifted
from the databases; nothing in update.sh calls it.
"""

import argparse, hashlib, json, sys, time

SECONDS_PER_DAY = 86400
# What update.sh passes resolve.py. The two must agree, or the seeded rows
# are spread over the wrong number of days.
DEFAULT_RECHECK_OLDEST = 1200


def read_repos(path):
    """The (owner, repo) pairs one JSON-lines database names."""
    repos = set()
    try:
        fh = open(path)
    except FileNotFoundError:
        return repos
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            e = json.loads(line)
            repos.add((e["owner"], e["repo"]))
    return repos


def span_seconds(rows, recheck_oldest):
    """How long a full pass over `rows` takes, at one run a day.

    A ledger smaller than one run's worth still spans a day, and so does a
    ledger whose re-checks are turned off: the stagger is taken modulo
    this, so zero is not an answer.
    """
    if recheck_oldest <= 0:
        return SECONDS_PER_DAY
    days = -(-rows // recheck_oldest)
    return max(days, 1) * SECONDS_PER_DAY


def stagger(key, span):
    """How far to backdate one row, deterministically from its name.

    Every row seeded at the same instant would come due on the same day.
    A hash spreads them across the cadence instead, and being a hash rather
    than a counter means re-running the seed on a repaired ledger does not
    reshuffle the rows that survived.
    """
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big") % span


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default="candidates.jsonl")
    ap.add_argument("--resolved", default="resolved.jsonl")
    ap.add_argument(
        "--recheck-oldest",
        type=int,
        default=DEFAULT_RECHECK_OLDEST,
        metavar="N",
        help="how many rows a run re-checks, which sets the cadence to spread over",
    )
    args = ap.parse_args()

    candidates = read_repos(args.candidates)
    resolved = read_repos(args.resolved)
    rejected = sorted(candidates - resolved)

    span = span_seconds(len(rejected), args.recheck_oldest)
    now = int(time.time())
    for owner, repo in rejected:
        checked_at = now - stagger(f"{owner}/{repo}", span)
        row = {"owner": owner, "repo": repo, "checked_at": checked_at}
        print(json.dumps(row, sort_keys=True))

    print(
        f"# {len(rejected)} rejected of {len(candidates)} candidates, "
        f"spread over {span // SECONDS_PER_DAY} day(s)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
