"""分支状态 API."""

import os
import subprocess
from fastapi import APIRouter, Query
from loop_engineering.path_utils import resolve_project_root

router = APIRouter()


@router.get("/list")
def list_branches(project: str = Query(None), filter: str = Query("")):
    """列出 agent 分支及其合入状态，默认按提交时间降序（最新在前），支持按 agent 名筛选."""
    pr = resolve_project_root(project=project)

    try:
        # 使用 git for-each-ref 按提交时间降序排列
        result = subprocess.run(
            'git for-each-ref --sort=-committerdate --format="%(refname:short)" refs/remotes/origin/agent/',
            shell=True, capture_output=True, text=True, cwd=pr, timeout=10
        )
        lines = result.stdout.strip().split("\n")
    except Exception:
        return {"branches": []}

    branches = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        branch = line.replace("origin/", "")

        # 按 agent 名筛选（分支名格式: agent/<whoami>/<task_id>-<slug>）
        if filter:
            parts = branch.split("/")
            if len(parts) < 2 or parts[0] != "agent" or parts[1] != filter:
                continue

        # 检查是否已合入
        merged = _is_merged(pr, branch)

        branches.append({
            "name": branch,
            "merged": merged,
        })

    return {"branches": branches}


def _is_merged(project_root, branch):
    """判断远程分支是否已合入 master."""
    import subprocess as sp
    try:
        r = sp.run(
            f"git merge-base --is-ancestor origin/{branch} origin/master",
            shell=True, capture_output=True, cwd=project_root, timeout=10
        )
        if r.returncode == 0:
            return True
        r = sp.run(
            f"git branch -r --merged origin/master",
            shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace', cwd=project_root, timeout=10
        )
        return branch in [l.strip() for l in r.stdout.strip().split("\n")]
    except Exception:
        return False
