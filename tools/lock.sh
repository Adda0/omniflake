#!/usr/bin/env bash
# Lock the generated flake, quarantining subflakes that cannot be locked.
#
# A megaflake is only as lockable as its worst member. Flakes in the wild
# fail for reasons outside our control: a stale committed flake.lock that
# forces Nix to re-resolve inputs, an indirect registry reference that no
# longer resolves (`flake:flake`), a deleted upstream repo. One such flake
# aborts the entire lock, so each failure is recorded in blocklist.txt and
# the flake is regenerated without it.
set -uo pipefail
cd "$(dirname "$0")/.."

SRC="${1:-resolved.jsonl}"
BLOCKLIST=blocklist.txt
MAX_ATTEMPTS="${MAX_ATTEMPTS:-400}"
touch "$BLOCKLIST"

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  # Regenerate excluding everything quarantined so far.
  python3 - "$SRC" "$BLOCKLIST" > filtered.jsonl <<'PY'
import json, sys
blocked = set(open(sys.argv[2]).read().split())
for line in open(sys.argv[1]):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if json.loads(line)["name"] in blocked:
        continue
    print(line)
PY
  python3 tools/generate.py < filtered.jsonl > flake.nix 2>/dev/null
  git add -N flake.nix >/dev/null 2>&1

  err=$(nix flake lock 2>&1)
  if [[ $? -eq 0 ]]; then
    echo "==> locked after ${attempt} attempt(s); $(wc -l < "$BLOCKLIST") quarantined"
    rm -f filtered.jsonl
    exit 0
  fi

  # The first top-level input named in the trace is the one that failed.
  bad=$(grep -oP "while updating the flake input '\K[^/']+" <<<"$err" | head -1)
  if [[ -z "$bad" ]]; then
    echo "==> lock failed with no identifiable input:" >&2
    tail -20 <<<"$err" >&2
    exit 1
  fi
  echo "$bad" >> "$BLOCKLIST"
  echo "  [$attempt] quarantined: $bad"
done

echo "==> gave up after ${MAX_ATTEMPTS} attempts" >&2
exit 1
