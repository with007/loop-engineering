"""模板重新部署 API — 一键将所有模板重新部署到 .claude/."""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from loop_engineering.path_utils import resolve_project_root
from loop_engineering.config import read_config

router = APIRouter()


@router.post("/deploy")
def sync_deploy(project: str = Query(None)):
    """重新部署所有模板到 .claude/：skills, commands, settings, scripts, docs, MCP, agent sync."""
    pr = resolve_project_root(project=project)
    cfg = read_config(pr)
    if not cfg:
        return HTMLResponse(content=_msg("fail", "配置不存在，请先运行 setup"))

    try:
        from loop_engineering.setup import deploy_managed_files
        deploy_managed_files(cfg)
    except Exception as e:
        return HTMLResponse(content=_msg("fail", f"部署失败: {e}"))

    return HTMLResponse(content=_msg("pass", "已部署: Skills/Commands/Settings, Scripts, Docs, MCP, Agent"))


def _msg(status, text):
    color = "var(--pass)" if status == "pass" else "var(--fail)"
    bg = "var(--pass-bg)" if status == "pass" else "var(--fail-bg)"
    return f"""<div class='card' style='border-color: {color}; background: {bg}; margin-bottom: 16px;'>
<p style='margin:0;font-size:14px;'>{text}</p>
</div>"""
