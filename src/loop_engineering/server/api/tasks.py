"""任务管理 API."""

import os
import re
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _slugify(desc):
    """与 task_pick.py 相同的 slugify 逻辑."""
    import hashlib
    desc = re.split(r'\s+—\s+', desc.strip())[0].strip().replace(' ', '-').lower()
    result = re.sub(r'[^a-z0-9-]', '', desc)
    result = re.sub(r'^-+|-+$', '', result)
    if len(result) < 3:
        result = 'task-' + hashlib.md5(desc.encode('utf-8')).hexdigest()[:8]
    return result[:40]


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


@router.delete("/{task_id}")
def delete_task(task_id: str, project: str = Query(None)):
    """删除任务及对应的 agent 分支。task_id 为 slugified description."""
    import subprocess
    pr = _project_root(project)
    tasks_path = os.path.join(pr, "tasks.md")
    if not os.path.exists(tasks_path):
        raise HTTPException(404, "tasks.md not found")

    deleted_line = None
    lines = []
    with open(tasks_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        m = re.match(r'^- \[(.)\]\s+(.+)', line)
        if m:
            rest = m.group(2).strip()
            # 拆出描述（去掉 assignee 和 meta 部分）
            desc = re.split(r'\s+[—(]', rest)[0].strip()
            if _slugify(desc) == task_id:
                deleted_line = line
                continue
        new_lines.append(line)

    if deleted_line is None:
        raise HTTPException(404, f"Task '{task_id}' not found")

    with open(tasks_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # 删除对应的 agent 分支
    branch_deleted = []
    branch_msg = ""
    try:
        r = subprocess.run('git branch --list "agent/*"', shell=True, capture_output=True, text=True, cwd=pr, timeout=5)
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b.endswith(f"/{task_id}"):
                # detach 当前 worktree 再删分支
                subprocess.run(f"git checkout --detach master 2>/dev/null", shell=True, cwd=pr, timeout=5)
                subprocess.run(f"git branch -D {b}", shell=True, capture_output=True, cwd=pr, timeout=5)
                branch_deleted.append(b)
        if branch_deleted:
            branch_msg = f", deleted branches: {', '.join(branch_deleted)}"
    except Exception as e:
        branch_msg = f", branch cleanup failed: {e}"

    return {"deleted": True, "task_id": task_id, "message": f"Task '{task_id}' removed{branch_msg}"}
