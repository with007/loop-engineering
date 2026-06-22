"""项目配置编辑 & 移除 API."""

import os
from fastapi import APIRouter, HTTPException, Query, Form
from fastapi.responses import HTMLResponse

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


# ── endpoints ──

@router.get("/current")
def get_config(project: str = Query(None)):
    """返回当前配置和可用 presets（供 Ajax 调用）."""
    from loop_engineering.config import read_config
    from loop_engineering.presets import list_presets

    pr = _project_root(project)
    cfg = read_config(pr)

    return {
        "config": cfg,
        "presets": [{"key": k, "name": n, "desc": d} for k, n, d in list_presets()],
    }


@router.post("/update")
def update_config(
    project: str = Query(None),
    project_name: str = Form(""),
    agent_name: str = Form(""),
    agent_mcp_port: int = Form(9080),
    main_mcp_port: int = Form(8080),
    type: str = Form(""),
    data_repo_path: str = Form(""),
):
    """表单提交：合并写入配置，端口变化时自动重生成 MCP 配置."""
    from loop_engineering.config import read_config, write_config, merge_config
    from loop_engineering.presets import apply_preset

    pr = _project_root(project)
    if not os.path.exists(os.path.join(pr, "loop-config.yaml")):
        raise HTTPException(404, "loop-config.yaml not found")

    updates = {
        "project": {"name": project_name},
        "agent": {
            "name": agent_name or None,
            "mcp_port": agent_mcp_port,
        },
        "main": {"mcp_port": main_mcp_port},
        "data_repo": {"path": data_repo_path} if data_repo_path else None,
    }

    new_config, changed = merge_config(pr, updates)

    # 校验端口
    for key, port in [
        ("main.mcp_port", new_config.get("main", {}).get("mcp_port")),
        ("agent.mcp_port", new_config.get("agent", {}).get("mcp_port")),
    ]:
        if port is not None and (not isinstance(port, int) or port < 1024 or port > 65535):
            raise HTTPException(400, f"{key} must be 1024-65535")

    # 类型 / preset
    if type and type != new_config.get("type"):
        new_config = apply_preset(new_config, type)
        changed.add("type")

    write_config(pr, new_config)

    # 副作用
    actions = []
    if changed & {"agent.mcp_port", "main.mcp_port"}:
        try:
            from loop_engineering.setup import generate_mcp_configs, sync_to_agent
            generate_mcp_configs(new_config)
            sync_to_agent(new_config)
            actions.append("MCP config regenerated & synced")
        except Exception as e:
            actions.append(f"MCP update failed: {e}")

    if changed & {"agent.name", "project.name"}:
        try:
            from loop_engineering.setup import render_skill_md
            render_skill_md(new_config)
            actions.append("task-runner SKILL.md re-rendered")
        except Exception as e:
            actions.append(f"SKILL.md update failed: {e}")

    if "agent.workspace" in changed:
        actions.append("agent.workspace changed; existing worktrees not moved")

    msg = f"<div class='card' style='border-color: var(--pass); background: var(--pass-bg); margin-bottom: 16px;'><p style='margin:0;font-size:14px;'>Saved ({len(changed)} fields). {'; '.join(actions)}</p></div>"
    return HTMLResponse(content=msg)


@router.post("/teardown")
def teardown_project(
    project: str = Query(None),
    confirm_name: str = Form(""),
    force: bool = Form(False),
):
    """移除 loop-engineering 的 agent worktree 和注册表条目."""
    from loop_engineering.config import read_config

    pr = _project_root(project)
    cfg = read_config(pr)
    if not cfg:
        raise HTTPException(404, "loop-config.yaml not found")

    project_name = cfg.get("project", {}).get("name", os.path.basename(pr))

    if not confirm_name or confirm_name.strip() != project_name:
        raise HTTPException(400, f"Type '{project_name}' to confirm")

    from loop_engineering.setup import run_teardown
    result = run_teardown(pr, force=force, dry_run=False)

    if result["removed"]:
        from fastapi.responses import Response
        return Response(status_code=200, headers={"HX-Redirect": "/"})
    else:
        msg = "<div class='card' style='border-color: var(--fail); background: var(--fail-bg); margin-bottom:16px;'><p style='margin:0;font-size:14px;'>Teardown failed</p></div>"
        return HTMLResponse(content=msg)
