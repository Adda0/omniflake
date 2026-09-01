#!/usr/bin/env bash
# Downloads the pinned databases into the checkout, for the tools that read
# them as plain files.
#
# The site build gets these through nix/data.nix, which is hash-verified by
# Nix. The pipeline scripts open them directly, so they need real files in
# the working directory; this puts them there and verifies the same hash.
#
# A file already present is left alone: the pipeline rewrites these in place,
# and a run that has resolved but not yet cut a release holds bytes newer
# than the pin. Pass --force to replace them anyway.
#
# --check asks the opposite question: are the databases in this checkout
# the ones the pins name? The regeneration step in check.yml uses it, since
# a pruned pins.jsonl that never went into a cut would otherwise pass every
# gate silently.
#
# Usage:
#   tools/fetch-data.sh            # fetch what is missing
#   tools/fetch-data.sh --force    # re-fetch everything at its pin
#   tools/fetch-data.sh --check    # verify what is here, fetch nothing
set -euo pipefail

# The databases live in the caller's checkout, not next to this script:
# under `nix run` this file is a store copy. nix/tools.nix guarantees $PWD
# is a checkout before any of these run.
ROOT="${OMNIFLAKE_ROOT:-$PWD}"
PINS="$ROOT/data-pins.json"

FORCE=0
CHECK=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --check) CHECK=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -f "$PINS" ]; then
  echo "fetch-data: no $PINS" >&2
  exit 1
fi

base=$(python3 -c "import json; print(json.load(open('$PINS'))['baseUrl'])")
mapfile -t names < <(python3 -c "
import json
print('\n'.join(sorted(json.load(open('$PINS'))['files'])))
")

for name in "${names[@]}"; do
  dest="$ROOT/$name"
  read -r tag want < <(python3 -c "
import json
pin = json.load(open('$PINS'))['files']['$name']
print(pin['tag'], pin['narHash'])
")

  if [ "$CHECK" -eq 1 ]; then
    if [ ! -f "$dest" ]; then
      echo "fetch-data: $name is missing" >&2
      exit 1
    fi
    got=$(nix hash path --sri --type sha256 "$dest")
    if [ "$got" != "$want" ]; then
      echo "fetch-data: $name does not match its pin in $tag" >&2
      echo "  pinned $want" >&2
      echo "  got    $got" >&2
      echo "  cut a release with tools/cut-data-release.sh" >&2
      exit 1
    fi
    echo "    $name matches $tag"
    continue
  fi

  if [ -f "$dest" ] && [ "$FORCE" -eq 0 ]; then
    echo "    $name present, keeping it"
    continue
  fi

  echo "==> $name from $tag"
  tmp="$dest.tmp"
  curl -fsSL --retry 3 -o "$tmp" "$base/$tag/$name"

  # Fail closed: the pin is the only thing making a mutable release asset
  # trustworthy, so a mismatch is fatal rather than a warning.
  got=$(nix hash path --sri --type sha256 "$tmp")
  if [ "$got" != "$want" ]; then
    rm -f "$tmp"
    echo "fetch-data: $name hash mismatch" >&2
    echo "  pinned $want" >&2
    echo "  got    $got" >&2
    exit 1
  fi
  mv "$tmp" "$dest"
done
