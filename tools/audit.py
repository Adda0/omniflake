#!/usr/bin/env python3
"""Find subflakes that lock here but will break a consumer.

Locking omniflake successfully does not mean anyone can use it. A subflake
carrying a *relative* `path:` input resolves that path against the root
flake, so it points inside omniflake's own tree. Our lock succeeds; the
consumer's fails:

    error: Path 'flakes/apple-container/flake.nix' does not exist in
    Git repository ".../omniflake"

That failure surfaces only downstream, so it has to be audited for here.
Prints one offending subflake per line, suitable for appending to
blocklist.txt.
"""
import argparse, json, sys


def relative_path_offenders(nodes):
    """Top-level subflakes with a relative path: input anywhere beneath them."""
    offenders = set()

    def walk(key, top, seen):
        for _name, target in (nodes.get(key, {}).get("inputs") or {}).items():
            if not isinstance(target, str) or target in seen:
                continue
            locked = nodes.get(target, {}).get("locked", {})
            path = str(locked.get("path", ""))
            if locked.get("type") == "path" and not path.startswith("/"):
                offenders.add(top)
            walk(target, top, seen | {target})

    for subflake, key in (nodes.get("root", {}).get("inputs") or {}).items():
        if isinstance(key, str):
            walk(key, subflake, {key})
    return offenders


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lock", help="flake.lock to audit")
    args = ap.parse_args()

    nodes = json.load(open(args.lock))["nodes"]
    offenders = sorted(relative_path_offenders(nodes))
    for o in offenders:
        print(o)
    print(f"# {len(offenders)} subflake(s) would break a consumer",
          file=sys.stderr)


if __name__ == "__main__":
    main()
