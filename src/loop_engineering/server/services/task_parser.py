"""Tasks.md 解析与过滤服务 — 纯逻辑，无路由依赖."""

import os
import re
import subprocess

from loop_engineering.task_id import TaskLine, extract_task_id_from_branch


def parse_tasks(project_root):
    """解析 tasks.md 返回 TaskLine 列表（带 feedback 填充）。

    Args:
        project_root: 项目根目录路径

    Returns:
        list of TaskLine objects with feedback populated
    """
    tp = os.path.join(project_root, "tasks.md")
    if not os.path.exists(tp):
        return []

    # 收集已有的 agent 分支名（task_id -> branch_name）
    agent_branches = {}
    try:
        r = subprocess.run('git branch --list "agent/*"', shell=True, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', cwd=project_root, timeout=5)
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b:
                tid = extract_task_id_from_branch(b)
                if tid:
                    agent_branches[tid] = b
    except Exception:
        pass

    # 收集已合入 master 的分支名
    merged_branches = set()
    try:
        r = subprocess.run('git branch --merged master --list "agent/*"', shell=True,
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace', cwd=project_root, timeout=5)
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b:
                merged_branches.add(b)
    except Exception:
        pass

    result = []
    current_task = None
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            tl = TaskLine.parse(line.rstrip('\n'))
            if tl:
                current_task = tl
                result.append(tl)
            elif current_task and re.match(r'^\s{2,}\S', line):
                # indented continuation line = feedback
                current_task.feedback.append(line.strip())
    return result


# Status filter mapping: which statuses to include for each filter name
_STATUS_INCLUDE = {
    "pending": {" ", "pending"},
    "in_progress": {"~", "in_progress", "r", "reopen", "pending_merge"},
    "done": {"x", "done", "pending_merge"},
    "reopen": {"r", "reopen"},
    "pending_merge": {"pending_merge"},
}


def filter_tasks(tasks, status=None, order=None, filter_name=None):
    """对 TaskLine 列表进行状态过滤和排序。

    Args:
        tasks: TaskLine 列表
        status: 过滤状态（如 "pending", "in_progress", "done", "reopen"）
        order: 排序方式（None 保持原序，其他暂未实现）
        filter_name: agent 名过滤（暂未实现，预留给未来）

    Returns:
        过滤后的 TaskLine 列表
    """
    result = list(tasks)
    if status and status in _STATUS_INCLUDE:
        include = _STATUS_INCLUDE[status]
        result = [t for t in result if t.status in include]
    # order / filter_name 是未来扩展点，目前不实现具体逻辑
    return result
