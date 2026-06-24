"""任务管理 API."""

import os
import re
import subprocess
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from loop_engineering.task_id import parse_task_id, extract_task_id_from_branch

router = APIRouter()


def _match_task_id(line, task_id):
    """检查 tasks.md 行是否匹配给定 task_id."""
    return parse_task_id(line) == task_id


def _project_root(project: str = None):
    if project:
        return project
    env = os.environ.get("LOOP_PROJECT_ROOT")
    if env:
        return env
    # 向上搜索 git 仓库根目录（兜底：server 的 cwd 可能不是项目根）
    d = os.getcwd()
    for _ in range(10):
        if os.path.exists(os.path.join(d, ".git")) or os.path.exists(os.path.join(d, "loop-config.yaml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


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
            if parse_task_id(line) == task_id:
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
        r = subprocess.run('git branch --list "agent/*"', shell=True, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', cwd=pr, timeout=5)
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if extract_task_id_from_branch(b) == task_id:
                # detach 当前 worktree 再删分支
                subprocess.run(f"git checkout --detach master 2>/dev/null", shell=True, cwd=pr, timeout=5)
                subprocess.run(f"git branch -D {b}", shell=True, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', cwd=pr, timeout=5)
                branch_deleted.append(b)
        if branch_deleted:
            branch_msg = f", deleted branches: {', '.join(branch_deleted)}"
    except Exception as e:
        branch_msg = f", branch cleanup failed: {e}"

    return {"deleted": True, "task_id": task_id, "message": f"Task '{task_id}' removed{branch_msg}"}


@router.put("/{task_id}/reset")
def reset_task(task_id: str, project: str = Query(None)):
    """将进行中的任务 ([~]) 重置为待办 ([ ])，用于恢复被中断的任务."""
    pr = _project_root(project)
    tasks_path = os.path.join(pr, "tasks.md")
    if not os.path.exists(tasks_path):
        raise HTTPException(404, "tasks.md not found")

    lines = []
    with open(tasks_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found = False
    for i, line in enumerate(lines):
        m = re.match(r'^- \[(.)\]\s+(.+)', line)
        if not m:
            continue
        if m.group(1) != "~":
            continue
        if parse_task_id(line) == task_id:
            # 将 [~] 替换为 [ ]
            lines[i] = line.replace("- [~] ", "- [ ] ", 1)
            found = True
            break

    if not found:
        raise HTTPException(404, f"In-progress task '{task_id}' not found")

    with open(tasks_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"reset": True, "task_id": task_id, "message": f"Task '{task_id}' reset to pending"}


@router.get("/{task_id}/report")
def get_task_report(task_id: str, project: str = Query(None)):
    """搜索 git log 返回任务 commit 的完整报告（markdown）。"""
    pr = _project_root(project)

    # 搜所有分支中含 [task_id] 的 commit（[ ] 在 git grep 中是 regex，需转义）
    r = subprocess.run(
        ["git", "log", "--all", f"--grep=\\[{task_id}\\]", "--format=%H%n%B", "-1", "--no-merges"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=pr, timeout=10
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise HTTPException(404, f"No commit found for task '{task_id}'")

    output = r.stdout.strip()
    # 第一行是 commit hash，后面是完整 body
    parts = output.split("\n", 1)
    commit_hash = parts[0]
    body = parts[1] if len(parts) > 1 else ""

    return {"commit_hash": commit_hash, "body": body}
