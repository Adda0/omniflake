#!/usr/bin/env bash
# Refresh omniflake. resolved.jsonl is a database that is kept and added to,
# so the default run only discovers and pins flakes it does not already
# know about. Nothing here regenerates flake.nix: that file is static, and
# the artifact that changes is index.json.
#
#   ./tools/update.sh              discover new flakes, pin them, regenerate
#   ./tools/update.sh --refresh    also re-pin everything already known
#   ./tools/update.sh --no-harvest skip GitHub search; pin and regenerate
#
# PIN_JOBS controls how many `nix flake metadata` processes run at once.
# REFRESH_OLDEST is how many known flakes are re-resolved per run (2000).
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

# New candidates are resolved, and the known rows resolved longest ago are
# re-resolved, so every row comes round on a fixed cadence. With ~16,000
# rows and the default of 2,000 per run, a daily run refreshes each flake
# about every eight days. A repo whose HEAD did not move costs nothing
# beyond the lookup.
echo "==> resolving (incremental; names are sticky)"
python3 tools/resolve.py --known resolved.jsonl $REFRESH \
  --refresh-oldest "${REFRESH_OLDEST:-2000}" \
  < candidates.jsonl > resolved.new.jsonl 2> resolve.log
# Manually resolved, non-GitHub flakes cannot go through the GitHub API.
if [[ -f manual.resolved.jsonl ]]; then
  cat manual.resolved.jsonl >> resolved.new.jsonl
fi
python3 -c '
import json
seen = {}
for line in open("resolved.new.jsonl"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    e = json.loads(line)
    seen[(e["owner"], e["repo"])] = e
with open("resolved.jsonl", "w") as fh:
    for e in seen.values():
        fh.write(json.dumps(e) + "\n")
'
rm -f resolved.new.jsonl manual.resolved.jsonl
echo "    $(wc -l < resolved.jsonl) flakes in the database"

# A one-line description per repo, for the site's search. Only rows that
# lack one are asked about.
echo "==> describing"
python3 tools/describe.py 2>&1 | tail -1

echo "==> splitting off personal-configuration repos"
python3 tools/classify.py --rejected personal.jsonl < resolved.jsonl > library.jsonl

# Every flake is pinned by its own `nix flake metadata` run, in parallel.
# A revision already in pins.jsonl is never fetched again, so this costs
# only what is new since the last run.
echo "==> pinning with Nix"
python3 tools/pin.py --jobs "${PIN_JOBS:-16}" 2> >(tee pin.log >&2)

# A flake whose stale lock names a branch needs the GitHub API to resolve
# it, and that is quota-limited without a token, so the first pass runs
# without one and the failures get a second, authenticated pass.
echo "==> retrying failures with a token"
python3 tools/pin.py --jobs 8 --retry-failed --use-token 2> >(tee -a pin.log >&2)

echo "==> generating index.json"
python3 tools/generate.py

echo "==> checking that the index evaluates"
echo "    $(nix eval .#lib.count) flakes indexed"
