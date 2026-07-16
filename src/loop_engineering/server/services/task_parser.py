"""Task parser service — task filtering utilities."""

import os
import re
from loop_engineering.taskhelper import FEEDBACK_LINE_RE


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
