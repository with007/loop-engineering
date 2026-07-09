"""Project context service — build project list context for Dashboard."""

import os
import subprocess
from loop_engineering.registry import list_projects, register_project
from loop_engineering.config import is_project_dir, read_config
from loop_engineering.path_utils import get_default_branch
from .task_parser import parse_tasks


def _filter_agent_workspace_copies(project_list):
    """Filter out agent workspace copies: loop-config.yaml project.root != actual path."""
    result = []
    for p in project_list:
        try:
            cfg = read_config(p["root"])
            cfg_root = cfg.get("project", {}).get("root", "")
            if cfg_root and os.path.normcase(os.path.abspath(cfg_root)) != os.path.normcase(os.path.abspath(p["root"])):
                continue
        except Exception:
            pass
        result.append(p)
    return result


def build_projects_context(current_pr, agent_filter=""):
    """Build project list + current project info. Only includes projects with loop-config.yaml.

    Args:
        current_pr: current project root path.
        agent_filter: optional agent name to filter branches by.

    Returns:
        list of project dicts with tasks, pass_rate, branches info.
    """
    projects = list_projects()

    # Auto-register current project (only if loop-config.yaml exists)
    if is_project_dir(current_pr) and not any(
        os.path.normcase(p["root"]) == os.path.normcase(current_pr) for p in projects
    ):
        register_project(current_pr)
        projects = list_projects()

    # Filter out projects without loop-config.yaml
    projects = [p for p in projects if is_project_dir(p["root"])]
    # Filter out agent workspace copies
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

        # Branches — use git for-each-ref, sorted by commit time desc
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

                # Filter by agent name (branch format: agent/<whoami>/<task_id>-<slug>)
                if agent_filter:
                    parts = b.split("/")
                    if len(parts) < 2 or parts[0] != "agent" or parts[1] != agent_filter:
                        continue

                # Check merge status
                if ref.startswith("origin/"):
                    r2 = subprocess.run(
                        f"git merge-base --is-ancestor {ref} origin/{get_default_branch(pr)}",
                        shell=True, capture_output=True, cwd=pr, timeout=5
                    )
                    branches_list.append({"name": b, "merged": r2.returncode == 0})
                else:
                    r_merged = subprocess.run(
                        f"git branch --merged {get_default_branch(pr)} --list {b}", shell=True, capture_output=True,
                        text=True, encoding='utf-8', errors='replace', cwd=pr, timeout=5
                    )
                    branches_list.append({"name": b, "merged": r_merged.stdout.strip() != ""})
        except Exception:
            pass

        result.append({
            "name": p["name"],
            "root": pr,
            "is_current": pr == current_pr,
            "tasks": {
                "pending": sum(1 for t in tasks if t["status"] == "pending"),
                "in_progress": sum(1 for t in tasks if t["status"] in ("in_progress", "pending_merge", "reopen")),
                "done": sum(1 for t in tasks if t["status"] == "done"),
                "pending_merge": sum(1 for t in tasks if t["status"] == "pending_merge"),
            },
            "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
            "branches": branches_list,
        })

    return result
