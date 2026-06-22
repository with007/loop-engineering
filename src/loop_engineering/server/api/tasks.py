"""任务管理 API."""

import os
import re
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


class AddTaskRequest(BaseModel):
    description: str
    assignee: str


@router.get("/list")
def list_tasks(project: str = Query(None)):
    """解析 tasks.md 返回任务列表."""
    pr = _project_root(project)
    tasks_path = os.path.join(pr, "tasks.md")
    if not os.path.exists(tasks_path):
        return {"tasks": []}

    tasks = []
    with open(tasks_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^- \[(.)\]\s+(.+?)(\s+\(→\s*(\w+)\))?(\s+—\s+(.+))?$', line)
            if not m:
                continue
            status_char = m.group(1)
            desc = m.group(2).strip()
            assignee = m.group(4) if m.group(4) else ""
            meta = m.group(6) if m.group(6) else ""

            status_map = {" ": "pending", "~": "in_progress", "x": "done"}
            tasks.append({
                "description": desc,
                "status": status_map.get(status_char, "pending"),
                "assignee": assignee,
                "meta": meta,
            })

    return {"tasks": tasks}


@router.post("/add")
def add_task(req: AddTaskRequest, project: str = Query(None)):
    """添加任务到 tasks.md."""
    pr = _project_root(project)
    tasks_path = os.path.join(pr, "tasks.md")

    line = f"- [ ] {req.description} (→ {req.assignee})\n"

    if os.path.exists(tasks_path):
        with open(tasks_path, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(tasks_path, "w", encoding="utf-8") as f:
            f.write("# Tasks\n\n")
            f.write(line)

    return {"added": True, "description": req.description, "assignee": req.assignee}
