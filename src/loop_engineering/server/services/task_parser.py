"""Task parser service — unified tasks.md 解析 and filtering."""

import os
import re
import subprocess
from loop_engineering.task_id import parse_task_id, extract_task_id_from_branch, FEEDBACK_LINE_RE
from loop_engineering.git_utils import is_merged


def parse_tasks(project_root):
    """Parse tasks.md into a list of task dicts.

    Each dict includes: description, task_id, status, assignee, meta, feedback.

    Status resolution considers git branch state:
    - [x] with unmerged branch → "pending_merge"
    - [x] with merged branch → "done"
    """
    tp = os.path.join(project_root, "tasks.md")
    if not os.path.exists(tp):
        return []

    # Collect all agent branch names (local + remote) keyed by task_id
    # Local branches
    agent_branches = {}
    try:
        r = subprocess.run(
            'git branch --list "agent/*"',
            shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace', cwd=project_root, timeout=5
        )
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b:
                tid = extract_task_id_from_branch(b)
                if tid and tid not in agent_branches:
                    agent_branches[tid] = b
    except Exception:
        pass

    # Remote branches (only if no local match)
    try:
        r = subprocess.run(
            'git branch -r --list "origin/agent/*"',
            shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace', cwd=project_root, timeout=5
        )
        for line in r.stdout.strip().split("\n"):
            b = line.strip()
            if b:
                tid = extract_task_id_from_branch(b)
                if tid and tid not in agent_branches:
                    agent_branches[tid] = b
    except Exception:
        pass

    result = []
    current_task = None
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            # Match checkbox
            m = re.match(r'^- \[(.)\]\s+(.+)', line)
            if m:
                current_task = None  # new task starts
                status_char = m.group(1)
                rest = m.group(2).strip()

                # Extract (→ assignee) — may be before or after meta
                assignee = ""
                m_assignee = re.search(r'\(→\s*(\w+)\)', rest)
                if m_assignee:
                    assignee = m_assignee.group(1)
                    rest = (rest[:m_assignee.start()] + rest[m_assignee.end():]).strip()

                # Extract — meta
                meta = ""
                m_meta = re.search(r'\s+—\s+(.+)$', rest)
                if m_meta:
                    meta = m_meta.group(1).strip()
                    rest = rest[:m_meta.start()].strip()

                desc = rest
                # Remove [task-id] suffix
                desc = re.sub(r'\s+\[[a-f0-9]{8}\]\s*$', '', desc).strip()
                tid = parse_task_id(line) or ""
                if status_char == "x" and tid and tid in agent_branches:
                    branch = agent_branches[tid]
                    if is_merged(branch, is_remote=branch.startswith("origin/"), repo_path=project_root):
                        status = "done"
                    else:
                        status = "pending_merge"
                else:
                    s = {" ": "pending", "~": "in_progress", "x": "done", "r": "reopen"}
                    status = s.get(status_char, "pending")
                current_task = {
                    "description": desc,
                    "task_id": tid,
                    "status": status,
                    "assignee": assignee,
                    "meta": meta,
                    "feedback": [],
                }
                result.append(current_task)
            elif FEEDBACK_LINE_RE.match(line) and current_task:
                # Indented continuation line = feedback
                current_task["feedback"].append(line.strip())
    return result


def filter_tasks(tasks, status="pending,in_progress", order="desc", filter_name=""):
    """Filter and sort tasks by status, assignee name, and order.

    Args:
        tasks: list of task dicts (from parse_tasks).
        status: comma-separated status values; "in_progress" also includes
                "pending_merge" and "reopen"; "done" also includes "pending_merge".
        order: "desc" (newest first) or "asc" (oldest first).
        filter_name: if non-empty, only include tasks whose assignee matches
                     (case-insensitive).

    Returns:
        Filtered and sorted list of task dicts.
    """
    allowed = [s.strip() for s in status.split(",") if s.strip()]
    # "in_progress" filter also includes "pending_merge" and "reopen"
    if "in_progress" in allowed:
        allowed.extend(["pending_merge", "reopen"])
    # "done" filter also includes "pending_merge"
    if "done" in allowed:
        allowed.append("pending_merge")
    tasks = [t for t in tasks if t["status"] in allowed]
    # Filter by agent (assignee) name
    if filter_name:
        f_lower = filter_name.strip().lower()
        tasks = [t for t in tasks if t.get("assignee", "").lower() == f_lower]
    if order == "desc":
        tasks = list(reversed(tasks))
    return tasks


def tasklines_to_dicts(tasklines):
    """Convert taskline objects (dicts or future TaskLine objects) to dicts.

    Currently a pass-through for dicts; will handle TaskLine.format() when
    TaskLine dataclass is introduced.
    """
    if not tasklines:
        return []
    # If already dicts, return as-is
    if isinstance(tasklines[0], dict):
        return tasklines
    # Future: if TaskLine objects, convert via format()
    return tasklines
