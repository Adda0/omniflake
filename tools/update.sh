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

# The scripts come from next to this one, the data from the current
# directory. Those are the same place for ./tools/update.sh in a checkout,
# and deliberately different under `nix run .#update`, where this file is a
# store copy and only the caller's directory holds the databases.
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$PWD/index.json" ]; then
  echo "update.sh: run this from an omniflake checkout (no index.json in $PWD)" >&2
  exit 1
fi

# GitHub search, GraphQL and the authenticated pin pass all take the token
# from GH_TOKEN. CI sets it; locally it comes from the gh CLI's login.
export GH_TOKEN="${GH_TOKEN:-$(gh auth token 2>/dev/null || true)}"

HARVEST=1
REFRESH=""
for arg in "$@"; do
  case "$arg" in
    --refresh)    REFRESH="--refresh" ;;
    --no-harvest) HARVEST=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# resolved.jsonl, pins.jsonl and candidates.jsonl live on release cuts
# rather than in the tree. A fresh checkout has none of them; a working one
# keeps what it has, since the pipeline rewrites them in place.
echo "==> fetching the pinned databases"
bash "$HERE/fetch-data.sh"

if [[ $HARVEST -eq 1 ]]; then
  echo "==> harvesting candidates from GitHub"
  python3 "$HERE/harvest.py" > candidates.new.jsonl 2> harvest.log
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
python3 "$HERE/manual.py" manual.txt \
  --candidates candidates.jsonl --resolved manual.resolved.jsonl
sort -u candidates.jsonl -o candidates.jsonl
echo "    $(wc -l < candidates.jsonl) candidates known"

# New candidates are resolved, and the known rows resolved longest ago are
# re-resolved, so every row comes round on a fixed cadence. With ~16,000
# rows and the default of 2,000 per run, a daily run refreshes each flake
# about every eight days. A repo whose HEAD did not move costs nothing
# beyond the lookup.
echo "==> resolving (incremental; names are sticky)"
# Manually resolved, non-GitHub flakes cannot go through the GitHub API;
# --merge folds them in over any stale row for the same repository.
python3 "$HERE/resolve.py" --known resolved.jsonl $REFRESH \
  --refresh-oldest "${REFRESH_OLDEST:-2000}" \
  --merge manual.resolved.jsonl \
  < candidates.jsonl > resolved.new.jsonl 2> resolve.log
mv resolved.new.jsonl resolved.jsonl
rm -f manual.resolved.jsonl
echo "    $(wc -l < resolved.jsonl) flakes in the database"

# A one-line description per repo, for the site's search. Only rows that
# lack one are asked about.
echo "==> describing"
python3 "$HERE/describe.py" 2>&1 | tail -1

echo "==> splitting off personal-configuration repos"
python3 "$HERE/classify.py" --rejected personal.jsonl < resolved.jsonl > library.jsonl

# Every flake is pinned by its own `nix flake metadata` run, in parallel.
# A revision already in pins.jsonl is never fetched again, so this costs
# only what is new since the last run.
echo "==> pinning with Nix"
python3 "$HERE/pin.py" --jobs "${PIN_JOBS:-16}" 2> >(tee pin.log >&2)

# A flake whose stale lock names a branch needs the GitHub API to resolve
# it, and that is quota-limited without a token, so the first pass runs
# without one and the failures get a second, authenticated pass.
echo "==> retrying failures with a token"
python3 "$HERE/pin.py" --jobs 8 --retry-failed --use-token 2> >(tee -a pin.log >&2)

echo "==> generating index.json"
python3 "$HERE/generate.py"

echo "==> checking that the index evaluates"
echo "    $(nix eval .#lib.count) flakes indexed"
