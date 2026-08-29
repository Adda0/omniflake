#!/usr/bin/env bash
# Regenerate omniflake from scratch: harvest -> resolve -> generate -> lock.
#
# Locking fetches every subflake's source (nix must read each flake.nix to
# discover its inputs), so a full run downloads a lot and takes a while.
# Set OMNIFLAKE_TOP to build a smaller tier instead, e.g. OMNIFLAKE_TOP=300.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> harvesting candidates from GitHub"
python3 tools/harvest.py > candidates.jsonl 2> harvest.log

echo "==> resolving to pinned revisions"
python3 tools/resolve.py < candidates.jsonl > resolved.jsonl 2> resolve.log

echo "==> splitting off personal-configuration repos"
python3 tools/classify.py --rejected personal.jsonl < resolved.jsonl > library.jsonl
mv library.jsonl resolved.jsonl

if [[ -n "${OMNIFLAKE_TOP:-}" ]]; then
  echo "==> limiting to top ${OMNIFLAKE_TOP} by stars"
  sort -t: -k2 -rn < resolved.jsonl \
    | python3 -c 'import sys,json;rows=[json.loads(l) for l in sys.stdin];rows.sort(key=lambda r:-r["stars"]);[print(json.dumps(r)) for r in rows[:int(sys.argv[1])]]' \
    "${OMNIFLAKE_TOP}" > resolved.top.jsonl
  SRC=resolved.top.jsonl
else
  SRC=resolved.jsonl
fi

echo "==> generating flake.nix"
python3 tools/generate.py < "$SRC" > flake.nix

echo "==> locking (this is the slow part)"
./tools/lock.sh "$SRC"

echo "==> done: $(python3 -c 'import json;print(len(json.load(open("flake.lock"))["nodes"])-1)') lock nodes"
