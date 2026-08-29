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
  if [[ -f candidates.jsonl ]]; then
    sort -u candidates.jsonl candidates.new.jsonl > candidates.merged.jsonl
    mv candidates.merged.jsonl candidates.jsonl
  else
    cp candidates.new.jsonl candidates.jsonl
  fi
  rm -f candidates.new.jsonl
fi

# Hand-listed flakes that search will never find.
echo "==> adding manual entries"
python3 tools/manual.py manual.txt \
  --candidates candidates.jsonl --resolved manual.resolved.jsonl
sort -u candidates.jsonl -o candidates.jsonl
echo "    $(wc -l < candidates.jsonl) candidates known"

echo "==> resolving (incremental; names are sticky)"
python3 tools/resolve.py --known resolved.jsonl $REFRESH \
  < candidates.jsonl > resolved.new.jsonl 2> resolve.log
# Manually resolved, non-GitHub flakes cannot go through the GitHub API.
if [[ -f manual.resolved.jsonl ]]; then
  cat manual.resolved.jsonl >> resolved.new.jsonl
fi
python3 -c '
import json,sys
seen={}
for line in open("resolved.new.jsonl"):
    line=line.strip()
    if not line or line.startswith("#"): continue
    e=json.loads(line); seen[(e["owner"],e["repo"])]=e
for e in seen.values(): print(json.dumps(e))
' > resolved.jsonl
rm -f resolved.new.jsonl manual.resolved.jsonl
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

# Pass 1 is shallow. It exists to produce a lock we can read the transitive
# input graph out of, which is what the nested follows are derived from.
echo "==> pass 1: shallow lock"
./tools/lock.sh "$SRC"

# A subflake with a relative path: input locks here but breaks consumers.
echo "==> auditing for consumer breakage"
python3 tools/audit.py flake.lock >> blocklist.txt
sort -u blocklist.txt -o blocklist.txt

echo "==> deriving nested follows"
python3 tools/deepen.py flake.lock > deep-follows.json

echo "==> pass 2: deep lock"
rm -f flake.lock
DEEP_FOLLOWS=deep-follows.json ./tools/lock.sh "$SRC"

echo "==> done: $(python3 -c 'import json;print(len(json.load(open("flake.lock"))["nodes"])-1)') lock nodes"
