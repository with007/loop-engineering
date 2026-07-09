#!/usr/bin/env python3
"""打印 Git 仓库默认分支名（零依赖，纯 stdlib）。

由 loop setup 部署到 .claude/scripts/，供 SKILL.md 和 bash 命令调用。
用法: python git_default_branch.py

优先级: local master > local main > origin/master > origin/main
"""

import subprocess
import sys


def get_default_branch(repo_path=None):
    """获取默认分支引用，自动检测 master vs main。"""
    for ref in ["master", "main", "origin/master", "origin/main"]:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                capture_output=True, text=True,
                cwd=repo_path, timeout=10
            )
            if result.returncode == 0:
                return ref
        except (subprocess.TimeoutExpired, OSError):
            continue
    return "master"


if __name__ == "__main__":
    print(get_default_branch())
