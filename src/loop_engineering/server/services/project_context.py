"""项目上下文构建服务 — 纯逻辑，无路由依赖."""

import os
import subprocess

from loop_engineering.task_id import extract_task_id_from_branch
from loop_engineering.server.services.task_parser import parse_tasks


def _filter_agent_workspace_copies(project_list):
    """过滤掉 agent workspace 拷贝：loop-config.yaml 里的 project.root 和自身路径不一致."""
    from loop_engineering.config import read_config as _read_cfg
    result = []
    for p in project_list:
        try:
            cfg = _read_cfg(p["root"])
            cfg_root = cfg.get("project", {}).get("root", "")
            if cfg_root and os.path.normcase(os.path.abspath(cfg_root)) != os.path.normcase(os.path.abspath(p["root"])):
                continue
        except Exception:
            pass
        result.append(p)
    return result


def build_projects_context(current_pr, agent_filter=""):
    """构建项目列表 + 当前项目信息（仅包含有 loop-config.yaml 的项目）。

    Args:
        current_pr: 当前项目根目录
        agent_filter: agent 名筛选（可选）

    Returns:
        list of dict，每个项目包含 name, root, tasks, pass_rate, branches 等
    """
    from loop_engineering.registry import list_projects, register_project
    from loop_engineering.config import is_project_dir, read_config
    from loop_engineering.runlog import get_pass_rate

    projects = list_projects()

    # 自动注册当前项目
    if is_project_dir(current_pr) and not any(
        os.path.normcase(p["root"]) == os.path.normcase(current_pr) for p in projects
    ):
        register_project(current_pr)
        projects = list_projects()

    # 过滤掉没有 loop-config.yaml 的孤项目
    projects = [p for p in projects if is_project_dir(p["root"])]
    # 过滤掉 agent workspace 拷贝
    projects = _filter_agent_workspace_copies(projects)

    result = []
    for p in projects:
        pr = p["root"]
        cfg = {}
        try:
            cfg = read_config(pr)
        except Exception:
            pass
        tasks = parse_tasks(pr)
        passed, total, rate = get_pass_rate(pr, days=7)

        # branches — 用 git for-each-ref 获取 agent 分支
        branches_list = []
        seen = set()
        try:
            r = subprocess.run(
                'git for-each-ref --sort=-committerdate --format="%(refname:short)" refs/heads/agent/ refs/remotes/origin/agent/',
                shell=True, capture_output=True, text=True,
                encoding='utf-8', errors='replace', cwd=pr, timeout=5
            )
            for line in r.stdout.strip().split("\n"):
                ref = line.strip()
                if not ref:
                    continue
                b = ref.replace("origin/", "")
                if b in seen:
                    continue
                seen.add(b)

                if agent_filter:
                    parts = b.split("/")
                    if len(parts) < 2 or parts[0] != "agent" or parts[1] != agent_filter:
                        continue

                tid = extract_task_id_from_branch(b)
                branches_list.append({
                    "name": b,
                    "task_id": tid or "",
                })
        except Exception:
            pass

        result.append({
            "name": cfg.get("project", {}).get("name", os.path.basename(pr)),
            "root": pr,
            "tasks": {
                "pending": sum(1 for t in tasks if t.status == " "),
                "in_progress": sum(1 for t in tasks if t.status == "~"),
                "done": sum(1 for t in tasks if t.status == "x"),
                "reopen": sum(1 for t in tasks if t.status == "r"),
                "total": len(tasks),
            },
            "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
            "branches": branches_list,
        })

    return result
