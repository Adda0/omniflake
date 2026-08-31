#!/usr/bin/env python3
"""Harvest candidate flake repositories from GitHub.

GitHub caps any single search at 1000 results, however many match, and
offers no cursor past it. The repository search is therefore partitioned
into disjoint slices, each small enough to read to the end, and the union
across slices is the answer.

Star ranges are the first axis. A bucket that is still over the cap is
subdivided on creation date until every piece fits, so the partition is
derived from what the API reports rather than guessed once and left to
rot: a hand-tuned boundary silently starts dropping repositories the day
the bucket behind it crosses 1000, which is how two 3- and 5-star flakes
went missing (issue #2).

The 0-star bucket is the deliberate exception. It holds ~65,000
language:Nix repositories on its own, nearly all abandoned personal
configurations, and enumerating it would push ~55,000 rows through
resolve, describe and pin to find a handful of real libraries. It is
sampled by push date instead, so what it does return is what people have
touched most recently. A flake that anyone has starred at all leaves it
for the enumerated path.

Output: JSON lines of {owner, repo, stars}, deduplicated, on stdout.
"""

import json, os, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta

# Queries that reliably surface flake repositories. language:Nix is by far the
# largest source; the topics catch flake repos written mostly in other
# languages, which language:Nix would miss entirely.
QUERIES = [
    "language:Nix",
    "topic:nix-flake",
    "topic:nix-flakes",
    "topic:nixos-config",
    "topic:flakes",
    "topic:flake",
    "topic:nix",
    "topic:nixos",
    "topic:home-manager",
    "topic:nix-darwin",
    "topic:nixpkgs",
]

# Disjoint star buckets: every repository has exactly one star count, so
# these cover the query without overlapping. Any of them may still be over
# the cap; created_windows subdivides the ones that are.
STAR_RANGES = [
    ">=1000",
    "500..999",
    "200..499",
    "100..199",
    "50..99",
    "20..49",
    "10..19",
    "5..9",
    "3..4",
    "2",
    "1",
    "0",
]

RESULT_CAP = 1000
PER_PAGE = 100
MAX_PAGES = RESULT_CAP // PER_PAGE

# The one bucket that is sampled rather than enumerated; see the module
# docstring for why.
SAMPLED_STARS = "0"

# The windows the sampled bucket is read through, by last push. Each is far
# over the cap and truncates; splitting by activity at least spreads what
# comes back across the years instead of returning one era of the bucket.
PUSH_SLICES = [
    "<2021-01-01",
    "2021-01-01..2022-06-30",
    "2022-07-01..2023-06-30",
    "2023-07-01..2024-06-30",
    "2024-07-01..2025-06-30",
    ">=2025-07-01",
]

# Bisection floor for creation dates: GitHub itself is not older than this,
# so the range below covers every repository it can return.
GITHUB_EPOCH = date(2008, 1, 1)

# The authenticated search limit is 30 requests a minute. Counting a slice
# and reading its pages come out of the same quota, so every search request
# is paced, not just the paging.
SEARCH_INTERVAL = 2.0
_last_search = 0.0


def read_token():
    """Read the GitHub token once, in-process.

    Every `gh` invocation asks the system keyring to unlock, so shelling out
    per request means one prompt per request. Reading it once and driving the
    REST API directly costs a single prompt for the whole run.
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


def api(path, params):
    """One authenticated GET against the GitHub REST API."""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"https://api.github.com{path}?{qs}")
    req.add_header("Accept", "application/vnd.github+json")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as fh:
                return json.loads(fh.read().decode())
        except urllib.error.HTTPError as e:
            # 403/429 here is the secondary rate limit; back off and retry.
            if e.code in (403, 429):
                time.sleep(15 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(3)
    return None


def paced_search(params):
    """One repository search, never issued faster than the rate limit."""
    global _last_search
    wait = SEARCH_INTERVAL - (time.monotonic() - _last_search)
    if wait > 0:
        time.sleep(wait)
    _last_search = time.monotonic()
    return api("/search/repositories", params)


def count(q):
    """How many repositories a query matches, ignoring the result cap.

    total_count is the true size of the match; only the results it hands
    back are capped. None means the API did not answer, which the caller
    treats as "assume it fits" so a failed count costs coverage rather
    than dropping the slice on the floor.
    """
    data = paced_search({"q": q, "per_page": 1})
    if not data:
        return None
    return data.get("total_count")


def created_windows(query, stars, lo, hi):
    """Yield `created:` ranges covering [lo, hi] that each fit under the cap.

    The split is on creation date, not push date, because a creation date
    never moves: the partition one run computes is the one the next run
    computes, and no repository can slip between two windows by being
    pushed to in between.

    A range that is still over the cap once it is down to a single day is
    yielded anyway and truncates. There is no finer qualifier to split on,
    and no single day sees 1000 new Nix repositories.
    """
    total = count(f"{query} stars:{stars} created:{lo}..{hi}")

    # An empty range needs neither pages nor further splitting.
    if total == 0:
        return

    if total is None or total <= RESULT_CAP or lo == hi:
        yield f"{lo}..{hi}"
        return

    mid = lo + (hi - lo) // 2
    yield from created_windows(query, stars, lo, mid)
    yield from created_windows(query, stars, mid + timedelta(days=1), hi)


def search(query, stars, pushed=None, created=None):
    """Yield repos for one query slice, paging to the result cap."""
    q = f"{query} stars:{stars}"
    if pushed:
        q += f" pushed:{pushed}"
    if created:
        q += f" created:{created}"
    for page in range(1, MAX_PAGES + 1):
        data = paced_search({"q": q, "per_page": PER_PAGE, "page": page})
        if not data:
            return
        items = data.get("items", [])
        if not items:
            return
        for it in items:
            yield it
        if len(items) < PER_PAGE:
            return


def emit(items, seen):
    """Print any repo not already seen; return how many were new."""
    new = 0
    for it in items:
        full = it.get("full_name")
        if not full or full in seen:
            continue
        seen.add(full)
        owner, repo = full.split("/", 1)
        print(
            json.dumps(
                {
                    "owner": owner,
                    "repo": repo,
                    "stars": it.get("stargazers_count", 0),
                }
            ),
            flush=True,
        )
        new += 1
    return new


def main():
    if not TOKEN:
        print(
            "# warning: no token; unauthenticated search is 10 req/min", file=sys.stderr
        )
    seen = set()
    today = date.today()
    for query in QUERIES:
        for stars in STAR_RANGES:
            if stars == SAMPLED_STARS:
                for pushed in PUSH_SLICES:
                    emit(search(query, stars, pushed=pushed), seen)
                windows = len(PUSH_SLICES)
            else:
                # Ask how big the bucket is and split it until it is
                # readable, rather than assuming a fixed set of windows
                # still fits.
                windows = 0
                for created in created_windows(query, stars, GITHUB_EPOCH, today):
                    emit(search(query, stars, created=created), seen)
                    windows += 1

            print(
                f"# {query} stars:{stars} in {windows} window(s)"
                f" -> {len(seen)} total",
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    main()
