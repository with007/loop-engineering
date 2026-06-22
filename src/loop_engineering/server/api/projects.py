"""项目发现与概览 API."""

import os
import subprocess
from fastapi import APIRouter, Query

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


def _find_all_projects(pr=None):
    """扫描配置目录，发现所有 loop-config.yaml 项目."""
    if pr is None:
        pr = _project_root()
    projects = []
    # 当前项目
    cfg_path = os.path.join(pr, "loop-config.yaml")
    if os.path.exists(cfg_path):
        projects.append(_project_info(pr))

    # TODO: 后续支持从 ~/.config/loop-engineering/projects.yaml 读取多项目
    return projects


def _project_info(project_root):
    """读取项目的 loop-config.yaml 返回摘要."""
    from loop_engineering.config import read_config
    from loop_engineering.runlog import get_pass_rate

    cfg = read_config(project_root)
    name = cfg.get("project", {}).get("name", os.path.basename(project_root))

    # 任务计数
    tasks_path = os.path.join(project_root, "tasks.md")
    pending = in_progress = done = 0
    if os.path.exists(tasks_path):
        with open(tasks_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("- [ ]"):
                    pending += 1
                elif line.startswith("- [~]"):
                    in_progress += 1
                elif line.startswith("- [x]"):
                    done += 1

    # PASS 率
    passed, total, rate = get_pass_rate(project_root, days=7)

    # 未合入分支数
    branch_count = _count_agent_branches(project_root)

    return {
        "name": name,
        "root": project_root,
        "tasks": {"pending": pending, "in_progress": in_progress, "done": done},
        "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
        "unmerged_branches": branch_count,
    }


def _count_agent_branches(project_root):
    """统计未合入的 agent 分支数."""
    try:
        result = subprocess.run(
            "git branch -r", shell=True, capture_output=True, text=True, cwd=project_root, timeout=10
        )
        lines = result.stdout.strip().split("\n")
        return sum(1 for l in lines if "agent/" in l and "origin/agent/" in l)
    except Exception:
        return 0


@router.get("/list")
def list_projects(project: str = Query(None)):
    return {"projects": _find_all_projects(_project_root(project))}
