#!/usr/bin/env python3
"""Split resolved flakes into library and personal-configuration tiers.

A naive harvest is dominated by people's own machine configurations. They
are poor library members twice over: they expose no reusable outputs worth
importing, and they are the most likely to fail locking, because a personal
config accumulates stale committed locks and dead registry aliases that
nobody else ever exercises.

Reads resolved.jsonl on stdin. Writes the kept tier to stdout, and the
rejected entries to the path given by --rejected (if provided).
"""
import argparse, json, re, sys

# Repository names that indicate a personal machine configuration.
PERSONAL = re.compile(
    r"(dotfile|dot-file|nixos-config|nix-config|nixconfig|homelab|"
    r"^config$|^configs$|^nixos$|^nix$|^flake$|^my-|personal|"
    r"system-config|machines|hosts)",
    re.I,
)


def is_personal(entry):
    """True when the repo name looks like someone's own machine config."""
    return PERSONAL.search(entry["repo"]) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rejected", help="write filtered-out entries here")
    ap.add_argument("--invert", action="store_true",
                    help="keep the personal tier instead of the library tier")
    args = ap.parse_args()

    kept, dropped = [], []
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry = json.loads(line)
        personal = is_personal(entry)
        (dropped if personal != args.invert else kept).append(entry)

    for e in kept:
        print(json.dumps(e))

    if args.rejected:
        with open(args.rejected, "w") as fh:
            for e in dropped:
                fh.write(json.dumps(e) + "\n")

    print(f"# kept={len(kept)} dropped={len(dropped)}", file=sys.stderr)


if __name__ == "__main__":
    main()
