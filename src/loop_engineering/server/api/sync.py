"""模板重新部署 API — 一键将所有模板重新部署到 .claude/."""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from loop_engineering.path_utils import resolve_project_root
from loop_engineering.config import read_config

router = APIRouter()


@router.post("/deploy")
def sync_deploy(project: str = Query(None)):
    """重新部署所有模板到 .claude/：skills, commands, settings, scripts, docs, MCP."""
    pr = resolve_project_root(project=project)
    cfg = read_config(pr)
    if not cfg:
        return HTMLResponse(content=_msg("fail", "配置不存在，请先运行 setup"))

    results = []

    # Skills + Commands + Settings
    try:
        from loop_engineering.setup import deploy_skills
        deploy_skills(cfg)
        results.append("Skills/Commands/Settings")
    except Exception as e:
        results.append(f"Skills 失败: {e}")

    # Scripts
    try:
        from loop_engineering.setup import deploy_scripts
        deploy_scripts(cfg)
        results.append("Scripts")
    except Exception as e:
        results.append(f"Scripts 失败: {e}")

    # VERIFY.md / TEST.md
    try:
        from loop_engineering.setup import deploy_verify_docs
        deploy_verify_docs(cfg)
        results.append("Docs")
    except Exception as e:
        results.append(f"Docs 失败: {e}")

    # MCP config
    try:
        from loop_engineering.setup import generate_mcp_configs
        generate_mcp_configs(cfg)
        results.append("MCP")
    except Exception as e:
        results.append(f"MCP 失败: {e}")

    # 同步到 Agent worktree
    try:
        from loop_engineering.setup import sync_to_agent
        sync_to_agent(cfg)
        results.append("Agent")
    except Exception as e:
        results.append(f"Agent 同步失败: {e}")

    ok = [r for r in results if "失败" not in r]
    fail = [r for r in results if "失败" in r]

    msg_parts = []
    if ok:
        msg_parts.append(f"已部署: {', '.join(ok)}")
    if fail:
        msg_parts.append(f"失败: {'; '.join(fail)}")

    status = "fail" if fail else "pass"
    return HTMLResponse(content=_msg(status, " | ".join(msg_parts)))


def _msg(status, text):
    color = "var(--pass)" if status == "pass" else "var(--fail)"
    bg = "var(--pass-bg)" if status == "pass" else "var(--fail-bg)"
    return f"""<div class='card' style='border-color: {color}; background: {bg}; margin-bottom: 16px;'>
<p style='margin:0;font-size:14px;'>{text}</p>
</div>"""
