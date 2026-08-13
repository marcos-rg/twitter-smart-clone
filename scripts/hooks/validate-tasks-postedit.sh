#!/bin/bash
# PostToolUse hook: after any Edit/Write/MultiEdit that touches
# specification/tasks.md, run the consistency validator and feed
# errors back to the agent (exit code 2 = blocking feedback).

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INPUT="$(cat)"

# Only act when the edited file is tasks.md.
echo "$INPUT" | grep -q 'specification/tasks\.md' || exit 0

OUTPUT="$(python3 "$REPO_ROOT/scripts/tasks.py" validate 2>&1)"
if [ $? -ne 0 ]; then
  echo "tasks.md consistency check failed after your edit:" >&2
  echo "$OUTPUT" >&2
  echo "Fix these problems (prefer 'python3 scripts/tasks.py set-status <ID> <STATUS>' for status changes)." >&2
  exit 2
fi
exit 0
