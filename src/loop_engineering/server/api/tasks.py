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


class ReopenRequest(BaseModel):
    feedback: str = ""  # 多行反馈，用 \n 分隔


@router.get("/list")
def list_tasks(project: str = Query(None)):
    """解析 tasks.md 返回任务列表."""
    pr = _project_root(project)
    tasks_path = os.path.join(pr, "tasks.md")
    if not os.path.exists(tasks_path):
        return {"tasks": []}

    tasks = []
    current_task = None
    with open(tasks_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^- \[(.)\]\s+(.+?)(\s+\(→\s*(\w+)\))?(\s+—\s+(.+))?$', line)
            if m:
                current_task = None  # new task starts, flush previous
                status_char = m.group(1)
                desc = m.group(2).strip()
                assignee = m.group(4) if m.group(4) else ""
                meta = m.group(6) if m.group(6) else ""

                status_map = {" ": "pending", "~": "in_progress", "x": "done", "r": "reopen"}
                current_task = {
                    "description": desc,
                    "status": status_map.get(status_char, "pending"),
                    "assignee": assignee,
                    "meta": meta,
                    "feedback": [],
                }
                tasks.append(current_task)
            elif re.match(r'^\s{2,}\S', line) and current_task:
                # indented continuation line = feedback for the current task
                current_task["feedback"].append(line.strip())

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


@router.put("/{task_id}/reopen")
def reopen_task(task_id: str, req: ReopenRequest, project: str = Query(None)):
    """将已完成任务 ([x]) 重新打开为返工状态 ([r])，可选追加反馈缩进行."""
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
        if m.group(1) not in ("x",):
            # 只有已完成的任务才能 reopen
            if parse_task_id(line) == task_id and m.group(1) != "x":
                raise HTTPException(400, "Only completed tasks can be reopened")
            continue
        if parse_task_id(line) == task_id:
            lines[i] = line.replace("- [x] ", "- [r] ", 1)
            found = True

            # 在任务行后追加反馈缩进行
            if req.feedback.strip():
                feedback_lines = [f"  {fl}\n" for fl in req.feedback.strip().split("\n") if fl.strip()]
                # 找到插入位置：任务行之后、下一个非缩进非空行之前
                insert_at = i + 1
                while insert_at < len(lines) and (lines[insert_at].strip() == "" or lines[insert_at].startswith("  ")):
                    insert_at += 1
                # 移除旧的缩进行（如果有）
                del lines[i + 1:insert_at]
                for j, fl in enumerate(feedback_lines):
                    lines.insert(i + 1 + j, fl)
            break

    if not found:
        raise HTTPException(404, f"Completed task '{task_id}' not found")

    with open(tasks_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"reopened": True, "task_id": task_id, "message": f"Task '{task_id}' reopened as [r]"}


@router.get("/{task_id}/report")
def get_task_report(task_id: str, project: str = Query(None)):
    """搜索 git log 返回任务 commit 的多轮报告（markdown）。"""
    pr = _project_root(project)

    r = subprocess.run(
        ["git", "log", "--all", f"--grep=\\[{task_id}\\]", "--format=%H%n%ai%n%B%n---REPORT-END---",
         "--no-merges"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=pr, timeout=10
    )
    if r.returncode != 0 or not r.stdout.strip():
        raise HTTPException(404, f"No commit found for task '{task_id}'")

    reports = []
    blocks = r.stdout.strip().split("\n---REPORT-END---")
    for i, block in enumerate(blocks):
        if not block.strip():
            continue
        lines = block.strip().split("\n", 2)
        if len(lines) < 2:
            continue
        commit_hash = lines[0]
        date = lines[1]
        body = lines[2] if len(lines) > 2 else ""
        reports.append({
            "commit_hash": commit_hash,
            "date": date,
            "imp_round": len(blocks) - i,  # 最新的 imp 号最大
            "body": body,
        })

    return {"reports": reports}
