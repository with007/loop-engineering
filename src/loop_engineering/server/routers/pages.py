"""Page routes — full-page responses (wrapped in base.html for non-HTMX)."""

import os
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from ..dependencies import get_project_root, get_agent_name, render
from ..services.task_parser import parse_tasks, filter_tasks
from ..services.project_context import build_projects_context

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, project: str = Query(None), filter: str = Query("")):
    pr = get_project_root(request, q=project)
    from loop_engineering.registry import list_projects
    from loop_engineering.config import is_project_dir

    # If current dir is not a project, fall back to a registered one
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
    current = next((p for p in all_projects if p["is_current"]), all_projects[0] if all_projects else None)
    return render(request, "dashboard.html", {
        "request": request,
        "projects": all_projects,
        "current_root": pr,
        "current": current,
        "filter": filter,
    })


@router.get("/tasks")
async def tasks_page(
    request: Request,
    project: str = Query(None),
    order: str = Query("desc"),
    status: str = Query("pending,in_progress"),
    filter: str = Query(""),
):
    pr = get_project_root(request, q=project)
    tasks = parse_tasks(pr)
    tasks = filter_tasks(tasks, status=status, order=order, filter_name=filter)
    return render(request, "tasks.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "current_root": pr,
        "order": order,
        "status": status,
        "filter": filter,
    })


@router.get("/runs")
async def runs_page(request: Request, whoami: str = "", project: str = Query(None)):
    from loop_engineering.runlog import list_runs, get_pass_rate

    pr = get_project_root(request, q=project)
    entries = list_runs(pr, whoami=whoami or None, limit=100)
    passed, total, rate = get_pass_rate(pr, days=7)
    agents = list(set(e.get("whoami", "") for e in entries if e.get("whoami")))
    return render(request, "runs.html", {
        "request": request,
        "runs": entries,
        "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
        "agents": agents,
        "filter_whoami": whoami,
        "current_root": pr,
    })


@router.get("/control")
async def control_page(request: Request, project: str = Query(None)):
    from loop_engineering.control import get_status
    from loop_engineering.path_utils import resolve_control_root

    pr = get_project_root(request, q=project)
    cr = resolve_control_root(pr)
    return render(request, "control.html", {
        "request": request,
        "status": get_status(cr),
        "current_root": pr,
    })


@router.get("/settings")
async def settings_page(request: Request, project: str = Query(None)):
    from loop_engineering.config import read_config
    from loop_engineering.presets import list_presets

    pr = get_project_root(request, q=project)
    from loop_engineering.config import is_project_dir
    if not is_project_dir(pr):
        return RedirectResponse("/setup", status_code=303)

    cfg = read_config(pr)
    presets = [{"key": k, "name": n, "desc": d} for k, n, d in list_presets()]

    return render(request, "settings.html", {
        "request": request,
        "current_root": pr,
        "config": cfg,
        "presets": presets,
    })


@router.get("/setup")
async def setup_page(request: Request):
    import subprocess

    git_user = ""
    try:
        r = subprocess.run(
            "git config user.name", shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=5
        )
        git_user = r.stdout.strip()
    except Exception:
        pass
    return render(request, "setup.html", {"request": request, "git_user": git_user})
