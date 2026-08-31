#!/usr/bin/env bash
# Repoints data-pins.json at a dated release cut.
#
# Every file handed in gets an entry {tag, narHash} under its basename;
# entries for files not named are left where they are, so a cut that
# re-uploads only what moved leaves the rest pinned to the tag that froze
# them.
#
# The narHash is what nix/fetch-artifact.nix verifies, so a pin computed
# here fails closed against a tampered or re-uploaded asset.
#
# Usage:
#   tools/bump-data-pin.sh <tag> <file...>
#   tools/bump-data-pin.sh data-20260830 resolved.jsonl pins.jsonl
set -euo pipefail

# The databases live in the caller's checkout, not next to this script:
# under `nix run` this file is a store copy. nix/tools.nix guarantees $PWD
# is a checkout before any of these run.
ROOT="${OMNIFLAKE_ROOT:-$PWD}"
PINS="$ROOT/data-pins.json"

if [ $# -lt 2 ]; then
  echo "usage: $(basename "$0") <tag> <file...>" >&2
  exit 2
fi
TAG="$1"
shift

# nix hash path NAR-serializes the file, which is exactly what fetchurl with
# recursiveHash verifies. The list goes through a temp file because the
# heredoc below already owns stdin.
HASHES=$(mktemp)
trap 'rm -f "$HASHES"' EXIT
for f in "$@"; do
  if [ ! -f "$f" ]; then
    echo "bump-data-pin: $f is not a file" >&2
    exit 1
  fi
  printf '%s\t%s\n' "$(basename "$f")" "$(nix hash path --sri --type sha256 "$f")"
done > "$HASHES"

python3 - "$PINS" "$TAG" "$HASHES" <<'PY'
import json, os, sys

pins_file, tag, hashes = sys.argv[1:4]
pins = {
    "version": 1,
    "baseUrl": "https://github.com/fzakaria/omniflake/releases/download",
    "files": {},
}
if os.path.exists(pins_file):
    pins = json.load(open(pins_file))

updated = 0
for line in open(hashes):
    name, nar_hash = line.rstrip("\n").split("\t")
    entry = {"tag": tag, "narHash": nar_hash}
    if pins["files"].get(name) != entry:
        pins["files"][name] = entry
        updated += 1

json.dump(pins, open(pins_file, "w"), indent=1, sort_keys=True)
open(pins_file, "a").write("\n")
print(f"{pins_file}: {updated} pin(s) updated, {len(pins['files'])} total")
PY
