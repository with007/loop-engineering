"""Git 工具函数 — 分支合入检测等.

共享给 task_cleanup.py 和 branches.py 使用。
"""

import subprocess
import os


def _run(cmd, cwd=None):
    """运行 shell 命令，返回 CompletedProcess."""
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        encoding='utf-8', errors='replace', cwd=cwd, timeout=15
    )


def _has_remote(cwd=None):
    """判断仓库是否有 remote."""
    try:
        r = _run("git remote", cwd=cwd)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _detect_default_branch(cwd=None):
    """内联 get_default_branch 逻辑，依次检测 master/main/origin/master/origin/main."""
    for ref in ["master", "main", "origin/master", "origin/main"]:
        try:
            r = _run(f"git rev-parse --verify {ref}", cwd=cwd)
            if r.returncode == 0:
                return ref
        except Exception:
            continue
    return "master"


def is_merged(branch, base=None, is_remote=True, repo_path=None):
    """判断分支是否已合入默认分支.

    Args:
        branch: 分支名（远程如 'origin/agent/with/task-xxx'，本地如 'agent/with/task-xxx'）
        base: 默认分支名，默认自动检测 master/main
        is_remote: True 表示远程分支（有 origin/ 前缀），False 表示本地分支
        repo_path: git 仓库路径

    Returns:
        bool — True 表示已合入

    检测策略（远程分支）:
      1. 本地祖先检测 (merge-base --is-ancestor short base) — 用户本地 merge 后立刻生效
      2. 本地已合并列表 (branch --merged base)
      3. 远程已合并列表 (branch -r --merged origin/base) — 用户 push 后生效
      4. 远程祖先检测 (merge-base --is-ancestor origin/branch origin/base) — squash/rebase 兜底

    检测策略（本地分支）:
      1. 祖先检测
      2. 已合并列表
    """
    if base is None:
        base = _detect_default_branch(cwd=repo_path)

    has_remote = _has_remote(cwd=repo_path)

    if is_remote and has_remote:
        # 远程分支 — 本地检测优先（用户 merge 后还没 push 也能检测到）
        short = branch.replace('origin/', '')

        # 1. 本地祖先检测
        r = _run(f"git merge-base --is-ancestor {short} {base}", cwd=repo_path)
        if r.returncode == 0:
            return True

        # 2. 本地已合并列表
        r = _run(f"git branch --merged {base}", cwd=repo_path)
        if short in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True

        # 3. 远程已合并列表
        r = _run(f"git branch -r --merged origin/{base}", cwd=repo_path)
        if branch in [l.strip() for l in r.stdout.strip().split('\n')]:
            return True

        # 4. 远程祖先检测（squash/rebase 兜底）
        r = _run(f"git merge-base --is-ancestor origin/{short} origin/{base}", cwd=repo_path)
        if r.returncode == 0:
            return True

    else:
        # 本地分支（或无远端）
        b = branch.replace('origin/', '') if is_remote else branch

        # 1. 祖先检测
        r = _run(f"git merge-base --is-ancestor {b} {base}", cwd=repo_path)
        if r.returncode == 0:
            return True

        # 2. 已合并列表
        r = _run(f"git branch --merged {base}", cwd=repo_path)
        if b in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True

    return False
