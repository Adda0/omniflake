#!/usr/bin/env bash
# Cuts (or tops up) a dated data release: uploads every database whose bytes
# differ from what data-pins.json already pins, then repoints the pins.
#
# Cuts are change-driven. A run that only re-resolves a few thousand rows
# still rewrites resolved.jsonl, so in practice a daily cut uploads the two
# or three files that moved — a few MB. Assets on a dated tag are immutable
# by convention (never overwritten, never deleted); the narHash pins fail
# closed if the convention is ever violated.
#
# Needs `gh` authenticated with repo scope.
#
# Usage:
#   tools/cut-data-release.sh              # tag data-<today, UTC>
#   tools/cut-data-release.sh data-20260901
set -euo pipefail

# The databases live in the caller's checkout, not next to this script:
# under `nix run` this file is a store copy. nix/tools.nix guarantees $PWD
# is a checkout before any of these run.
ROOT="${OMNIFLAKE_ROOT:-$PWD}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="${1:-data-$(date -u +%Y%m%d)}"

# The databases that live on releases rather than in the flake tree. Keep
# this list in step with .gitignore and tools/fetch-data.sh.
FILES=(resolved.jsonl pins.jsonl candidates.jsonl)

CHANGED=()
for name in "${FILES[@]}"; do
  f="$ROOT/$name"
  if [ ! -f "$f" ]; then
    echo "cut-data-release: $name is missing; run the pipeline first" >&2
    exit 1
  fi
  current=$(nix hash path --sri --type sha256 "$f")
  pinned=$(python3 -c "
import json, os, sys
p = '$ROOT/data-pins.json'
pins = json.load(open(p)) if os.path.exists(p) else {'files': {}}
print(pins['files'].get('$name', {}).get('narHash', ''))
")
  if [ "$current" != "$pinned" ]; then
    CHANGED+=("$f")
  fi
done

if [ ${#CHANGED[@]} -eq 0 ]; then
  echo "cut-data-release: every database matches its pin; nothing to cut"
  exit 0
fi
echo "${#CHANGED[@]} database(s) changed since their pins"

# Assets on a dated tag are immutable, so a name already uploaded there is
# never replaced. A tag that already carries one of the files being cut --
# a second cut on the same day, usually a re-run after something failed --
# moves to the next free suffix instead. Topping up a tag with files it
# does not yet carry is still allowed, which is what keeps a normal cut on
# one tag per day.
BASE_TAG="$TAG"
for n in $(seq 1 20); do
  [ "$n" -eq 1 ] && TAG="$BASE_TAG" || TAG="$BASE_TAG-$n"
  if ! gh release view "$TAG" > /dev/null 2>&1; then
    break
  fi
  existing=$(gh release view "$TAG" --json assets --jq '.assets[].name')
  clash=0
  for f in "${CHANGED[@]}"; do
    if grep -qxF "$(basename "$f")" <<< "$existing"; then
      clash=1
      break
    fi
  done
  [ "$clash" -eq 0 ] && break
  TAG=""
done

if [ -z "$TAG" ]; then
  echo "cut-data-release: no free tag after 20 tries from $BASE_TAG" >&2
  exit 1
fi
echo "cutting into $TAG"

# A tag the loop settled on either does not exist yet, or exists and is
# missing every file being uploaded. The second case is a top-up, and
# `gh release create` never runs for it.
MODE="cut"
if gh release view "$TAG" > /dev/null 2>&1; then
  MODE="top-up"
fi

# What moved into the index in this run, rendered from the working tree
# against HEAD. That comparison holds because update.yml cuts before it
# commits, so HEAD is still the previous index; release-notes.py says so
# rather than reporting zeroes when it is not, and never fails the cut.
NOTES=$(mktemp)
BODY=$(mktemp)
trap 'rm -f "$NOTES" "$BODY"' EXIT
python3 "$HERE/release-notes.py" --root "$ROOT" --mode "$MODE" --files "${CHANGED[@]}" > "$NOTES"

# A top-up keeps the notes of the cut that opened the release -- they
# describe a different run -- and gains this cut's section below them.
if [ "$MODE" = "cut" ]; then
  gh release create "$TAG" \
    --title "Index databases, ${TAG#data-}" \
    --notes-file "$NOTES"
else
  {
    gh release view "$TAG" --json body --jq .body
    printf '\n---\n\n'
    cat "$NOTES"
  } > "$BODY"
  gh release edit "$TAG" --notes-file "$BODY"
fi

gh release upload "$TAG" "${CHANGED[@]}"
bash "$HERE/bump-data-pin.sh" "$TAG" "${CHANGED[@]}"
