#!/bin/bash
# Stop hook: prevent the agent from finishing while specification/tasks.md
# is inconsistent (exit code 2 = block stop and feed errors back).

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INPUT="$(cat)"

# Avoid infinite loops: if this hook already blocked once, let the agent stop.
echo "$INPUT" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && exit 0

OUTPUT="$(python3 "$REPO_ROOT/scripts/tasks.py" validate 2>&1)"
if [ $? -ne 0 ]; then
  echo "Cannot finish: specification/tasks.md is inconsistent:" >&2
  echo "$OUTPUT" >&2
  echo "Fix task statuses/counts (use 'python3 scripts/tasks.py set-status <ID> <STATUS>') before finishing." >&2
  exit 2
fi
exit 0
