#!/usr/bin/env bash
# Refresh omniflake. resolved.jsonl is a database that is kept and added to,
# so the default run only discovers and resolves flakes we do not already
# know about. Harvesting every repo from scratch is not the normal path.
#
#   ./tools/update.sh              discover new flakes, keep existing pins
#   ./tools/update.sh --refresh    also re-pin everything already known
#   ./tools/update.sh --no-harvest regenerate and lock from the current data
#
# OMNIFLAKE_TOP=300 limits the built tier to the top N by stars.
set -euo pipefail
cd "$(dirname "$0")/.."

HARVEST=1
REFRESH=""
for arg in "$@"; do
  case "$arg" in
    --refresh)    REFRESH="--refresh" ;;
    --no-harvest) HARVEST=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ $HARVEST -eq 1 ]]; then
  echo "==> harvesting candidates from GitHub"
  python3 tools/harvest.py > candidates.new.jsonl 2> harvest.log

  # Union with what we already had; discovery is cumulative.
  if [[ -f candidates.jsonl ]]; then
    sort -u candidates.jsonl candidates.new.jsonl > candidates.merged.jsonl
    mv candidates.merged.jsonl candidates.jsonl
  else
    cp candidates.new.jsonl candidates.jsonl
  fi
  rm -f candidates.new.jsonl
  echo "    $(wc -l < candidates.jsonl) candidates known"
fi

echo "==> resolving (incremental; names are sticky)"
python3 tools/resolve.py --known resolved.jsonl $REFRESH \
  < candidates.jsonl > resolved.new.jsonl 2> resolve.log
mv resolved.new.jsonl resolved.jsonl
echo "    $(wc -l < resolved.jsonl) flakes in the database"

echo "==> splitting off personal-configuration repos"
python3 tools/classify.py --rejected personal.jsonl < resolved.jsonl > library.jsonl

SRC=library.jsonl
if [[ -n "${OMNIFLAKE_TOP:-}" ]]; then
  echo "==> limiting to top ${OMNIFLAKE_TOP} by stars"
  python3 -c 'import sys,json;rows=[json.loads(l) for l in open(sys.argv[1])];rows.sort(key=lambda r:-r["stars"]);[print(json.dumps(r)) for r in rows[:int(sys.argv[2])]]' \
    library.jsonl "${OMNIFLAKE_TOP}" > resolved.top.jsonl
  SRC=resolved.top.jsonl
fi

echo "==> generating and locking"
./tools/lock.sh "$SRC"
