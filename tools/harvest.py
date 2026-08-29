#!/usr/bin/env python3
"""Harvest candidate flake repositories from GitHub.

GitHub caps any single search at 1000 results, so the repository search is
partitioned into disjoint star ranges and issued once per topic. Each slice
stays under the cap, and the union across slices approximates the full set.

Output: JSON lines of {owner, repo, stars}, deduplicated, on stdout.
"""
import json, os, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

# Queries that reliably surface flake repositories. language:Nix is by far the
# largest source; the topics catch flake repos written mostly in other
# languages, which language:Nix would miss entirely.
QUERIES = [
    "language:Nix",
    "topic:nix-flake", "topic:nix-flakes", "topic:nixos-config",
    "topic:flakes", "topic:flake", "topic:nix", "topic:nixos",
    "topic:home-manager", "topic:nix-darwin", "topic:nixpkgs",
]

# Disjoint star buckets keep every slice below GitHub's 1000-result cap.
STAR_RANGES = [
    ">=1000", "500..999", "200..499", "100..199", "50..99",
    "20..49", "10..19", "5..9", "3..4", "2", "1", "0",
]

PER_PAGE = 100
MAX_PAGES = 10  # 10 * 100 = the 1000-result cap

# The 0- and 1-star buckets are far larger than the cap, so they are split
# again by when the repo was last pushed.
DATE_SLICES = [
    "<2021-01-01", "2021-01-01..2022-06-30", "2022-07-01..2023-06-30",
    "2023-07-01..2024-06-30", "2024-07-01..2025-06-30", ">=2025-07-01",
]


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
        out = subprocess.run(["gh", "auth", "token"],
                             capture_output=True, text=True, timeout=60)
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


def search(query, stars, pushed=None):
    """Yield repos for one query slice, paging to the 1000-result cap."""
    q = f"{query} stars:{stars}"
    if pushed:
        q += f" pushed:{pushed}"
    for page in range(1, MAX_PAGES + 1):
        data = api("/search/repositories",
                   {"q": q, "per_page": PER_PAGE, "page": page})
        if not data:
            return
        items = data.get("items", [])
        if not items:
            return
        for it in items:
            yield it
        if len(items) < PER_PAGE:
            return
        # Stay inside the 30 req/min authenticated search limit.
        time.sleep(2.0)


def emit(items, seen):
    """Print any repo not already seen; return how many were new."""
    new = 0
    for it in items:
        full = it.get("full_name")
        if not full or full in seen:
            continue
        seen.add(full)
        owner, repo = full.split("/", 1)
        print(json.dumps({
            "owner": owner,
            "repo": repo,
            "stars": it.get("stargazers_count", 0),
        }), flush=True)
        new += 1
    return new


def main():
    if not TOKEN:
        print("# warning: no token; unauthenticated search is 10 req/min",
              file=sys.stderr)
    seen = set()
    for query in QUERIES:
        for stars in STAR_RANGES:
            # These buckets exceed the result cap, so slice them by date too.
            slices = DATE_SLICES if stars in ("0", "1", "2") else [None]
            for pushed in slices:
                emit(search(query, stars, pushed), seen)
            print(f"# {query} stars:{stars} -> {len(seen)} total",
                  file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
