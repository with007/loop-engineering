#!/usr/bin/env python3
"""从 tasks.md 选取下一个待办任务（独立部署版）。

零包依赖，纯 stdlib + git 命令。
由 loop setup 部署到 .claude/scripts/。
用法: python .claude/scripts/task_pick.py <username> [--project-root <dir>] [--format shell]
输出: taskID=<id> branch=<分支名> desc=<描述> openSpec=<true|false>  或  NONE（无任务） 或  BUSY（有进行中任务）
"""
import hashlib
import os
import re
import shlex
import subprocess
import sys

from task_line import find_project_root, load_tasks


# ── 工具函数 ──

def _run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def _make_readable_slug(description, max_len=40):
    """从描述生成可读的 git 分支名后缀."""
    desc = re.split(r'\s+—\s+', description.strip())[0].strip()
    desc = re.sub(r'[\\:?*\[\]~^{}!]', '', desc)
    desc = re.sub(r'\s+', '-', desc)
    desc = re.sub(r'-{2,}', '-', desc)
    desc = re.sub(r'\.{2,}', '', desc)
    desc = re.sub(r'^\.|\.$', '', desc)
    desc = re.sub(r'^-+|-+$', '', desc)
    result = desc[:max_len]
    if not result or len(result) < 1:
        result = 'task'
    return result


def _make_branch_name(whoami, task_id, description):
    slug = _make_readable_slug(description)
    return f"agent/{whoami}/{task_id}-{slug}"


# ── 主逻辑 ──

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_pick.py <username> [--project-root <path>] [--format shell]")
        sys.exit(1)

    whoami = sys.argv[1]
    project_root = None
    fmt = None
    for i, arg in enumerate(sys.argv):
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
        elif arg == "--format" and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]
    if not project_root:
        project_root = find_project_root()
    tasks_path = os.path.join(project_root, "tasks.md")

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
                         f"reopen={kwargs.get('reopen', 'false')}",
                         f"user_feedback={kwargs.get('user_feedback', '')}"]
                print(" ".join(parts))
            elif status == "none":
                print("NONE")
            elif status == "busy":
                print("BUSY")

    from task_line import load_tasks

    entries = load_tasks(tasks_path)
    tasks = [tl for tl, _ in entries if tl and tl.assignee == whoami]

    for tl in tasks:
        if tl.status == "~":
            emit("busy")
            return

    for tl in tasks:
        if tl.status not in (" ", "r"):
            continue
        if not tl.task_id:
            continue

        desc = tl.description
        task_id = tl.task_id
        is_reopen = tl.status == "r"

        if is_reopen:
            r = _run(f"git branch -a --list 'agent/{whoami}/{task_id}-*' --sort=-committerdate")
            branches = [b.strip().lstrip('* ') for b in r.stdout.strip().split('\n') if b.strip()]
            if branches:
                branch = branches[0]
                if branch.startswith('remotes/origin/'):
                    branch = branch[len('remotes/origin/'):]
            else:
                # 本地无分支记录 → 尝试 reflog 恢复
                expected = _make_branch_name(whoami, task_id, desc)
                r3 = _run(f"git reflog origin/{expected} --format=%H -1")
                if r3.returncode == 0 and r3.stdout.strip():
                    old_hash = r3.stdout.strip()
                    r4 = _run(f"git fetch origin {old_hash}")
                    if r4.returncode == 0:
                        _run(f"git branch {expected} {old_hash}")
                        branch = expected
                        print(f"NOTE: [r] task {task_id} — branch recovered from reflog ({old_hash[:8]})",
                              file=sys.stderr)
                    else:
                        print(f"WARNING: [r] task {task_id} — reflog found {old_hash[:8]} but fetch failed, skipping.",
                              file=sys.stderr)
                        continue
                else:
                    print(f"WARNING: [r] task {task_id} — branch not found (local/reflog), skipping.",
                          file=sys.stderr)
                    continue
        else:
            branch = _make_branch_name(whoami, task_id, desc)

        open_spec = "true" if (
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{desc}")) or
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{task_id}"))
        ) else "false"
        reopen_flag = "true" if is_reopen else "false"

        emit("ok", task_id=task_id, branch=branch, desc=desc, openSpec=open_spec, reopen=reopen_flag,
             user_feedback="\n".join(tl.feedback) if tl.feedback else "")
        return

    emit("none")


if __name__ == "__main__":
    main()
