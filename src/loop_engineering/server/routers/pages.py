"""Page routes — 返回完整页面的路由（/, /tasks, /runs, /control, /settings, /setup）."""

import os
from urllib.parse import quote

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse

from loop_engineering.path_utils import resolve_project_root
from loop_engineering.server.dependencies import templates, render_page, get_agent_name
from loop_engineering.server.services.task_parser import parse_tasks, filter_tasks, tasklines_to_dicts
from loop_engineering.server.services.project_context import build_projects_context

router = APIRouter()


def _get_filtered_task_dicts(pr, status, filter_str, order):
    """Parse, filter, and return task dicts for template rendering."""
    tasklines = parse_tasks(pr)
    filtered = filter_tasks(tasklines, status=status, filter_name=filter_str, order=order)
    return tasklines_to_dicts(filtered)


# ── Page routes ──

@router.get("/")
async def dashboard(request: Request, project: str = Query(None), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    from loop_engineering.registry import list_projects
    from loop_engineering.config import is_project_dir

    if not is_project_dir(pr):
        projects = list_projects()
        valid = [p for p in projects if is_project_dir(p["root"])]
        if valid:
            redir = f"/?project={quote(valid[0]['root'])}"
            if filter:
                redir += f"&filter={quote(filter)}"
            return RedirectResponse(redir, status_code=303)
        else:
            return RedirectResponse("/setup", status_code=303)

    all_projects = build_projects_context(pr, agent_filter=filter)
    current = next((p for p in all_projects if p.get("is_current")), all_projects[0] if all_projects else None)
    if current is None:
        current = {"root": pr, "name": os.path.basename(pr)}
        current["is_current"] = True
    return render_page(request, "dashboard.html", {
        "request": request,
        "projects": all_projects,
        "current_root": pr,
        "current": current,
        "filter": filter,
    })


@router.get("/tasks")
async def tasks_page(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _get_filtered_task_dicts(pr, status, filter, order)
    return render_page(request, "tasks.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "current_root": pr,
        "order": order,
        "status": status,
        "filter": filter,
    })


@router.get("/runs")
async def runs_page(request: Request, project: str = Query(None), order: str = Query(""), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    runs_entries = []
    import glob, json
    runs_dir = os.path.join(pr, ".loop-engineering", "runs")
    if os.path.isdir(runs_dir):
        for fpath in sorted(glob.glob(os.path.join(runs_dir, "*.json")), reverse=True):
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    entry = json.load(fh)
                if filter and entry.get("whoami", "") != filter:
                    continue
                runs_entries.append({
                    "task_id": entry.get("task_id", ""),
                    "task_desc": entry.get("task_desc", ""),
                    "whoami": entry.get("whoami", ""),
                    "phase": entry.get("phase", ""),
                    "result": entry.get("result", ""),
                    "imp_round": entry.get("imp_round", 1),
                    "vfy_round": entry.get("vfy_round", 1),
                    "completed": entry.get("completed", ""),
                })
            except Exception:
                pass
    return render_page(request, "runs.html", {
        "request": request,
        "runs": runs_entries,
        "current_root": pr,
        "filter": filter,
    })


@router.get("/control")
async def control_page(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return render_page(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


@router.get("/settings")
async def settings_page(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return render_page(request, "settings.html", {
        "request": request,
        "current_root": pr,
    })


@router.get("/setup")
async def setup_page(request: Request, project: str = Query(None)):
    """Setup wizard — always served standalone (no base.html wrapping)."""
    pr = resolve_project_root(project=project)
    from loop_engineering.config import detect_config
    detected = detect_config(pr)
    return templates.TemplateResponse(request, "setup.html", {
        "request": request,
        "detected_name": detected.get("project", {}).get("name", ""),
        "detected_workspace": detected.get("agent", {}).get("workspace", ""),
        "detected_user": detected.get("agent", {}).get("name", ""),
        "detected_unity": bool(detected.get("_detected", {}).get("unity")),
        "detected_data_repo": detected.get("data_repo", {}).get("path", ""),
        "presets": [
            {"key": "unity-tolua", "name": "Unity + ToLua", "desc": "PVP 卡牌项目"},
            {"key": "python-server", "name": "Python Server", "desc": "Python CLI/Server 项目（loop-engineering 同类）"},
            {"key": "generic", "name": "Generic", "desc": "通用项目（无特定语言/framework）"},
        ],
        "current_root": pr,
    })
