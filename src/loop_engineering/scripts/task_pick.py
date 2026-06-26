#!/usr/bin/env python3
"""
从 tasks.md 选取下一个待办任务。
用法: python -m loop_engineering.scripts.task_pick <username>
输出: taskID=<id> branch=<分支名> desc=<描述> openSpec=<true|false>  或  NONE（无任务） 或  BUSY（有进行中任务）

从当前目录向上查找 loop-config.yaml 定位项目根目录。
"""
import subprocess, sys, re, os
from loop_engineering.task_id import parse_task_id, make_branch_name
from loop_engineering.config import is_project_dir


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def _find_project_root():
    """从 cwd 向上查找 loop-config.yaml，定位项目根目录."""
    p = os.getcwd()
    for _ in range(10):
        if is_project_dir(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.getcwd()  # fallback


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_pick.py <username> [--project-root <path>]")
        sys.exit(1)

    whoami = sys.argv[1]
    project_root = None
    for i, arg in enumerate(sys.argv):
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
            break
    if not project_root:
        project_root = _find_project_root()
    tasks_path = os.path.join(project_root, "tasks.md")

    try:
        with open(tasks_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print("NONE")
        return

    # 如果当前用户已有进行中的任务，不再选新任务
    for line in content.split('\n'):
        if re.match(r'^- \[~\]\s+.+?\s+\(→\s*' + re.escape(whoami) + r'\)', line):
            print("BUSY")
            return

    for line in content.split('\n'):
        match = re.match(r'^- \[[ r]\]\s+(.+?)\s+\(→\s*' + re.escape(whoami) + r'\)', line)
        if not match:
            continue

        desc = match.group(1).strip()
        task_id = parse_task_id(line)
        if not task_id:
            continue  # 没有 [task-id] 的任务跳过

        # 判断是否 reopen
        is_reopen = line.startswith('- [r] ')

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

        print(f"taskID={task_id} branch={branch} desc={desc} openSpec={open_spec} reopen={reopen_flag}")
        return

    print("NONE")


if __name__ == "__main__":
    main()
