#!/usr/bin/env python3
"""Output project variables as shell eval-able format.

Usage: eval $(python .claude/scripts/project_vars.py)
Sets: PROJECT_ROOT, AGENT_DIR, AGENT_PORT, AGENT_WS_LAST, DEFAULT_REF, TASKS_PATH, HAS_DATA_REPO, DATA_REPO_NAME
"""
import os, sys, yaml
from taskhelper import find_project_root


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = find_project_root()
    cfg = {}
    for name in [".loop-engineering/loop-config.yaml", "loop-config.yaml"]:
        path = os.path.join(p, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            break

    project_root = (cfg.get("project_root") or cfg.get("project", {}).get("root") or p).replace("\\", "/")
    agent_workspace = cfg.get("agent", {}).get("workspace", os.getcwd()).replace("\\", "/")
    agent_dir = agent_workspace + "/loop-engineering"
    agent_ws_last = agent_workspace.rstrip("/").split("/")[-1]
    agent_port = str(cfg.get("agent", {}).get("mcp_port", 9080))
    default_ref = cfg.get("default_ref", "master")
    tasks_path = project_root + "/tasks.md"
    data_repo = cfg.get("data_repo")
    has_data_repo = "true" if data_repo else "false"
    data_repo_name = data_repo.get("name", "") if data_repo else ""

    for k, v in [
        ("PROJECT_ROOT", project_root),
        ("AGENT_DIR", agent_dir),
        ("AGENT_WS", agent_workspace),
        ("AGENT_PORT", agent_port),
        ("AGENT_WS_LAST", agent_ws_last),
        ("DEFAULT_REF", default_ref),
        ("TASKS_PATH", tasks_path),
        ("HAS_DATA_REPO", has_data_repo),
        ("DATA_REPO_NAME", data_repo_name),
    ]:
        escaped = v.replace("'", "'\\''")
        print(f"{k}='{escaped}'")


if __name__ == "__main__":
    main()
