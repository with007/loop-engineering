#!/usr/bin/env python3
"""
从 tasks.md 选取下一个待办任务。
用法: python -m loop_engineering.scripts.task_pick <username>
输出: taskID=<id> branch=<分支名> desc=<描述> openSpec=<true|false>  或  NONE（无任务） 或  BUSY（有进行中任务）

从当前目录向上查找 loop-config.yaml 定位项目根目录。
"""
import subprocess, sys, re, os, shlex
from loop_engineering.task_id import TaskLine, make_branch_name
from loop_engineering.path_utils import find_project_root


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_pick.py <username> [--project-root <path>] [--format shell]")
        sys.exit(1)

    whoami = sys.argv[1]
    project_root = None
    fmt = None  # None = default legacy format
    for i, arg in enumerate(sys.argv):
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
        elif arg == "--format" and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]
    if not project_root:
        project_root = find_project_root()
    tasks_path = os.path.join(project_root, "tasks.md")

    # Helper to output in the requested format
    def emit(status, **kwargs):
        if fmt == "shell":
            print(f"STATUS={status}")
            for k, v in kwargs.items():
                print(f"{k}={shlex.quote(str(v))}")
        else:
            if status == "ok":
                parts = [f"taskID={kwargs.get('task_id', '')}",
                         f"branch={kwargs.get('branch', '')}",
                         f"desc={kwargs.get('desc', '')}",
                         f"openSpec={kwargs.get('openSpec', 'false')}",
                         f"reopen={kwargs.get('reopen', 'false')}"]
                print(" ".join(parts))
            elif status == "none":
                print("NONE")
            elif status == "busy":
                print("BUSY")

    try:
        with open(tasks_path, 'r', encoding='utf-8') as f:
            lines = f.read().split('\n')
    except FileNotFoundError:
        emit("none")
        return

    # 解析所有任务行
    tasks = []
    for line in lines:
        tl = TaskLine.parse(line)
        if tl and tl.assignee == whoami:
            tasks.append(tl)

    # 如果当前用户已有进行中的任务，不再选新任务
    for tl in tasks:
        if tl.status == "~":
            emit("busy")
            return

    for tl in tasks:
        if tl.status not in (" ", "r"):
            continue
        if not tl.task_id:
            continue  # 没有 [task-id] 的任务跳过

        desc = tl.description
        task_id = tl.task_id
        is_reopen = tl.status == "r"

        if is_reopen:
            # 查找已有 agent 分支
            r = run(f"git branch -a --list 'agent/{whoami}/{task_id}-*' --sort=-committerdate")
            branches = [b.strip().lstrip('* ') for b in r.stdout.strip().split('\n') if b.strip()]
            if branches:
                # 取最新分支（含 remote 前缀则取本地名）
                branch = branches[0]
                if branch.startswith('remotes/origin/'):
                    branch = branch[len('remotes/origin/'):]
            else:
                # 分支不存在，退化为新任务
                branch = make_branch_name(whoami, task_id, desc)
                is_reopen = False
        else:
            branch = make_branch_name(whoami, task_id, desc)

        # 检查是否已有同名远程分支（新任务才检查）
        if not is_reopen:
            result = run(f"git ls-remote --heads origin 'agent/{whoami}/{task_id}-*'")
            if result.stdout.strip():
                continue  # 跳过已有分支的新任务

        # OpenSpec 目录用 slug 命名（如 refactor-core-architecture），不是 hash（f610728e）
        # 优先匹配 desc（即 slug），兼容直接用 task_id 的情况
        open_spec = "true" if (
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{desc}")) or
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{task_id}"))
        ) else "false"
        reopen_flag = "true" if is_reopen else "false"

        emit("ok", task_id=task_id, branch=branch, desc=desc, openSpec=open_spec, reopen=reopen_flag)
        return

    emit("none")


if __name__ == "__main__":
    main()
