#!/usr/bin/env python3
"""Merge candidate pools into one row per repository.

update.sh used to fold a fresh harvest into candidates.jsonl with
`sort -u`, which deduplicates identical *lines*. A repository whose star
count changed between harvests produces a different line, so both survived
and the pool grew a row every time. The pool held 24,941 lines for 24,547
repositories when this was written, and every duplicate was queried again
on every run.

The rest of the pipeline already treats the pool as a set of repositories:
resolve.py keys on (owner, repo). This makes the file agree with that.

Files are read in the order given, oldest first, and a later row wins, so
the fresh harvest decides a repository's star count. Output goes to stdout
sorted by (owner, repo) with sorted keys, so a run that learns nothing
new produces no diff.

    tools/merge-candidates.py candidates.jsonl candidates.new.jsonl
"""

import argparse, json, sys


def read_rows(path):
    """Yield the candidate rows in one pool, comments and blanks skipped."""
    try:
        fh = open(path)
    except FileNotFoundError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            yield json.loads(line)


def merge(pools):
    """Fold pools of candidate rows into one row per repository.

    The key is the exact (owner, repo) pair, which is what resolve.py keys
    on too: two spellings of the same repository are two repositories to
    the whole pipeline, and collapsing them here alone would only move the
    disagreement.
    """
    by_repo = {}
    for pool in pools:
        for row in pool:
            by_repo[(row["owner"], row["repo"])] = row
    return [by_repo[key] for key in sorted(by_repo)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pools", nargs="+", metavar="FILE", help="oldest pool first")
    args = ap.parse_args()

    rows = merge(read_rows(p) for p in args.pools)
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    print(f"# {len(rows)} candidate repositories", file=sys.stderr)


if __name__ == "__main__":
    main()
