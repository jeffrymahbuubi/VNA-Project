#!/usr/bin/env bash
# Dedupe claude-flow auto-memory vector store.
# Procedure documented in docs/claude-flow-101.md (Vector Accumulation section).
#
# Usage:
#   scripts/dedup_vector_store.sh                  # dry-run: diagnose only
#   scripts/dedup_vector_store.sh --apply          # backup + dedup + prune derived
#   scripts/dedup_vector_store.sh --apply --no-backup
#
# Resolves project root from script location, so it can be run from any cwd.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/.claude-flow/data"
STORE="$DATA_DIR/auto-memory-store.json"
GRAPH="$DATA_DIR/graph-state.json"
RANKED="$DATA_DIR/ranked-context.json"

APPLY=0
BACKUP=1
for arg in "$@"; do
  case "$arg" in
    --apply)     APPLY=1 ;;
    --no-backup) BACKUP=0 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "unknown flag: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$STORE" ]]; then
  echo "no auto-memory-store.json at $STORE" >&2
  exit 1
fi

echo "=== Diagnose ($DATA_DIR) ==="
ls -lh "$DATA_DIR"
echo
python3 - "$STORE" <<'PY'
import json, sys
from collections import Counter
data = json.load(open(sys.argv[1]))
seen = {}
for e in data:
    key = e.get('key') or e.get('id')
    prev = seen.get(key)
    if prev is None or e.get('updatedAt', 0) >= prev.get('updatedAt', 0):
        seen[key] = e
print(f'Total entries:   {len(data)}')
print(f'Unique by key:   {len(seen)}')
print(f'Duplicates:      {len(data) - len(seen)}')
print('Namespaces:     ', dict(Counter(e.get('namespace','?') for e in data).most_common()))
PY

if [[ "$APPLY" -ne 1 ]]; then
  echo
  echo "Dry-run only. Re-run with --apply to execute dedup + prune derived files."
  exit 0
fi

DUPS=$(python3 - "$STORE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
s = {}
for e in d:
    k = e.get('key') or e.get('id')
    p = s.get(k)
    if p is None or e.get('updatedAt',0) >= p.get('updatedAt',0):
        s[k] = e
print(len(d) - len(s))
PY
)

if [[ "$DUPS" -eq 0 && ! -f "$GRAPH" && ! -f "$RANKED" ]]; then
  echo
  echo "Already clean — no duplicates, no stale derived files. Nothing to do."
  exit 0
fi

if [[ "$BACKUP" -eq 1 ]]; then
  STAMP="$(date +%Y-%m-%d_%H%M%S)"
  BACKUP_DIR="$DATA_DIR/.backup-$STAMP"
  mkdir -p "$BACKUP_DIR"
  for f in "$STORE" "$GRAPH" "$RANKED"; do
    [[ -f "$f" ]] && cp "$f" "$BACKUP_DIR/"
  done
  echo
  echo "=== Backup: $BACKUP_DIR ==="
  ls -lh "$BACKUP_DIR"
fi

echo
echo "=== Apply dedup ==="
python3 - "$STORE" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
seen = {}
for e in data:
    key = e.get('key') or e.get('id')
    prev = seen.get(key)
    if prev is None or e.get('updatedAt', 0) >= prev.get('updatedAt', 0):
        seen[key] = e
deduped = list(seen.values())
json.dump(deduped, open(path, 'w'), indent=2)
print(f'Wrote {len(deduped)} entries (removed {len(data)-len(deduped)})')
PY

echo
echo "=== Prune stale derived files (auto-regenerate next session) ==="
rm -fv "$GRAPH" "$RANKED" || true

echo
echo "=== Verify ==="
ls -lh "$DATA_DIR"
echo
echo "Done. Restart Claude Code or /clear so the in-memory vector index reloads."
