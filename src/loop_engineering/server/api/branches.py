"""分支状态 API."""

import os
import subprocess
from fastapi import APIRouter, Query

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


@router.get("/list")
def list_branches(project: str = Query(None)):
    """列出 agent 分支及其合入状态."""
    pr = _project_root(project)

    try:
        # 列出远程 agent 分支
        result = subprocess.run(
            "git branch -r", shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace', cwd=pr, timeout=10
        )
        lines = result.stdout.strip().split("\n")
    except Exception:
        return {"branches": []}

    branches = []
    for line in lines:
        line = line.strip()
        if "agent/" not in line:
            continue
        branch = line.replace("origin/", "")

        # 检查是否已合入
        merged = _is_merged(pr, branch)

        branches.append({
            "name": branch,
            "merged": merged,
        })

    # 按合入状态排序：未合入的排前面
    branches.sort(key=lambda b: (b["merged"], b["name"]))
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
