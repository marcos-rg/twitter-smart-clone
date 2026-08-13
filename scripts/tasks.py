#!/usr/bin/env python3
"""Task tracker helper for specification/tasks.md.

Subcommands:
  next                     Print the next eligible task (resumes In Progress first).
  list                     List all tasks with status and dependencies.
  show <ID>                Print a task's full markdown section.
  set-status <ID> <STATUS> Update a task's status and the progress counts table.
  validate                 Check tasks.md consistency; exit 1 on problems.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_FILE = REPO_ROOT / "specification" / "tasks.md"
STATUSES = ("To Do", "In Progress", "Done")
TASK_HEADING = re.compile(r"^### (TSC-[A-Z]+-\d{3}) - (.+)$")
DEP_ID = re.compile(r"TSC-[A-Z]+-\d{3}")


@dataclass
class Task:
    id: str
    title: str
    heading_line: int  # 0-based index into lines
    status: str = ""
    status_line: int = -1
    deps: list[str] = field(default_factory=list)


def read_lines() -> list[str]:
    return TASKS_FILE.read_text(encoding="utf-8").splitlines()


def collect_bullet(lines: list[str], start: int) -> str:
    """Return a full bullet starting at `start`, joining wrapped continuation lines."""
    parts = [lines[start]]
    i = start + 1
    while i < len(lines) and lines[i].startswith("  ") and not lines[i].lstrip().startswith("- **"):
        parts.append(lines[i].strip())
        i += 1
    return " ".join(p.strip() for p in parts)


def parse_tasks(lines: list[str]) -> list[Task]:
    tasks: list[Task] = []
    current: Task | None = None
    for i, line in enumerate(lines):
        m = TASK_HEADING.match(line)
        if m:
            current = Task(id=m.group(1), title=m.group(2), heading_line=i)
            tasks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("- **Status:**") and current.status_line == -1:
            current.status = line.split("**Status:**", 1)[1].strip()
            current.status_line = i
        elif line.startswith("- **Dependencies:**") and not current.deps:
            bullet = collect_bullet(lines, i)
            current.deps = DEP_ID.findall(bullet.split("**Dependencies:**", 1)[1])
    return tasks


def by_id(tasks: list[Task]) -> dict[str, Task]:
    return {t.id: t for t in tasks}


def next_eligible(tasks: list[Task]) -> tuple[Task | None, str]:
    in_progress = [t for t in tasks if t.status == "In Progress"]
    if in_progress:
        t = in_progress[0]
        warn = "; WARNING: multiple tasks In Progress" if len(in_progress) > 1 else ""
        return t, f"resume (already In Progress{warn})"
    index = by_id(tasks)
    for t in tasks:
        if t.status != "To Do":
            continue
        blockers = [d for d in t.deps if index.get(d) is None or index[d].status != "Done"]
        if not blockers:
            return t, "start (all dependencies Done)"
    return None, ""


def cmd_next() -> int:
    tasks = parse_tasks(read_lines())
    task, reason = next_eligible(tasks)
    if task is None:
        if all(t.status == "Done" for t in tasks):
            print("All tasks are Done. Project complete.")
        else:
            print("No eligible task: every To Do task has unfinished dependencies.")
            index = by_id(tasks)
            for t in tasks:
                if t.status == "To Do":
                    blockers = [d for d in t.deps if index.get(d) is None or index[d].status != "Done"]
                    print(f"  {t.id} blocked by: {', '.join(blockers)}")
        return 1
    print(f"{task.id} - {task.title}")
    print(f"Status: {task.status}")
    print(f"Action: {reason}")
    print(f"Dependencies: {', '.join(task.deps) or 'None'}")
    return 0


def cmd_list() -> int:
    for t in parse_tasks(read_lines()):
        deps = ", ".join(t.deps) or "None"
        print(f"{t.id:<14} {t.status:<12} deps: {deps}")
    return 0


def cmd_show(task_id: str) -> int:
    lines = read_lines()
    tasks = parse_tasks(lines)
    index = by_id(tasks)
    if task_id not in index:
        print(f"Unknown task ID: {task_id}", file=sys.stderr)
        return 1
    start = index[task_id].heading_line
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if TASK_HEADING.match(lines[i]) or lines[i].startswith("## "):
            end = i
            break
    print("\n".join(lines[start:end]).rstrip())
    return 0


def rewrite_counts(lines: list[str], tasks: list[Task]) -> None:
    counts = {s: sum(1 for t in tasks if t.status == s) for s in STATUSES}
    for i, line in enumerate(lines):
        for status in STATUSES:
            if re.match(rf"^\| {re.escape(status)} \|", line):
                lines[i] = f"| {status} | {counts[status]} |"


def cmd_set_status(task_id: str, new_status: str) -> int:
    if new_status not in STATUSES:
        print(f"Invalid status {new_status!r}. Use one of: {', '.join(STATUSES)}", file=sys.stderr)
        return 1
    lines = read_lines()
    tasks = parse_tasks(lines)
    index = by_id(tasks)
    task = index.get(task_id)
    if task is None:
        print(f"Unknown task ID: {task_id}", file=sys.stderr)
        return 1
    if new_status == "Done":
        blockers = [d for d in task.deps if index.get(d) is None or index[d].status != "Done"]
        if blockers:
            print(
                f"Refusing to mark {task_id} Done: dependencies not Done: {', '.join(blockers)}",
                file=sys.stderr,
            )
            return 1
    old = task.status
    lines[task.status_line] = f"- **Status:** {new_status}"
    task.status = new_status
    rewrite_counts(lines, tasks)
    TASKS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{task_id}: {old} -> {new_status} (counts table updated)")
    return 0


def cmd_validate() -> int:
    lines = read_lines()
    tasks = parse_tasks(lines)
    errors: list[str] = []
    index: dict[str, Task] = {}
    for t in tasks:
        if t.id in index:
            errors.append(f"Duplicate task ID: {t.id}")
        index[t.id] = t
        if t.status_line == -1:
            errors.append(f"{t.id}: missing Status line")
        elif t.status not in STATUSES:
            errors.append(f"{t.id}: invalid status {t.status!r}")
    for t in tasks:
        for d in t.deps:
            if d not in index:
                errors.append(f"{t.id}: unknown dependency {d}")
            elif t.status == "Done" and index[d].status != "Done":
                errors.append(f"{t.id} is Done but dependency {d} is {index[d].status!r}")
    in_progress = [t.id for t in tasks if t.status == "In Progress"]
    if len(in_progress) > 1:
        errors.append(f"Multiple tasks In Progress: {', '.join(in_progress)}")
    counts = {s: sum(1 for t in tasks if t.status == s) for s in STATUSES}
    for line in lines:
        m = re.match(r"^\| (To Do|In Progress|Done) \| (\d+) \|$", line)
        if m and counts[m.group(1)] != int(m.group(2)):
            errors.append(
                f"Progress table says {m.group(1)} = {m.group(2)}, actual is {counts[m.group(1)]}"
            )
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(
        f"tasks.md OK: {len(tasks)} tasks ({counts['Done']} Done, "
        f"{counts['In Progress']} In Progress, {counts['To Do']} To Do)"
    )
    return 0


def main(argv: list[str]) -> int:
    if not TASKS_FILE.exists():
        print(f"Not found: {TASKS_FILE}", file=sys.stderr)
        return 1
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 1
    cmd, args = argv[1], argv[2:]
    if cmd == "next":
        return cmd_next()
    if cmd == "list":
        return cmd_list()
    if cmd == "show" and len(args) == 1:
        return cmd_show(args[0])
    if cmd == "set-status" and len(args) == 2:
        return cmd_set_status(args[0], args[1])
    if cmd == "validate":
        return cmd_validate()
    print(__doc__.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
