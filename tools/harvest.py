#!/usr/bin/env python3
"""Harvest candidate flake repositories from GitHub.

GitHub caps any single search at 1000 results, so the repository search is
partitioned into disjoint star ranges and issued once per topic. Each slice
stays under the cap, and the union across slices approximates the full set.

Output: JSON lines of {owner, repo, stars}, deduplicated, on stdout.
"""
import json, subprocess, sys, time

# Topics that reliably tag flake repositories.
TOPICS = ["nix-flake", "nix-flakes", "nixos-config", "flakes", "nix", "nixos"]

# Disjoint star buckets keep every slice below GitHub's 1000-result cap.
STAR_RANGES = [
    ">=1000", "500..999", "200..499", "100..199", "50..99",
    "20..49", "10..19", "5..9", "3..4", "2", "1", "0",
]

PER_PAGE = 100
MAX_PAGES = 10  # 10 * 100 = the 1000-result cap


def gh(args):
    """Run a gh api call, returning parsed JSON or None on failure."""
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=90)
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def search(topic, stars):
    """Yield repos for one (topic, star-range) slice, paging to the cap."""
    for page in range(1, MAX_PAGES + 1):
        q = f"topic:{topic} stars:{stars}"
        data = gh([
            "gh", "api", "-X", "GET", "search/repositories",
            "-f", f"q={q}", "-f", f"per_page={PER_PAGE}", "-f", f"page={page}",
        ])
        if not data:
            return
        items = data.get("items", [])
        if not items:
            return
        for it in items:
            yield it
        if len(items) < PER_PAGE:
            return
        # Stay well inside the 30 req/min search rate limit.
        time.sleep(2.0)


def main():
    seen = set()
    for topic in TOPICS:
        for stars in STAR_RANGES:
            for it in search(topic, stars):
                full = it["full_name"]
                if full in seen:
                    continue
                seen.add(full)
                owner, repo = full.split("/", 1)
                print(json.dumps({
                    "owner": owner,
                    "repo": repo,
                    "stars": it.get("stargazers_count", 0),
                }), flush=True)
            print(f"# {topic} stars:{stars} -> {len(seen)} total", file=sys.stderr)


if __name__ == "__main__":
    main()
