"""HTMX fragment routes — 返回 HTML 片段的路由.

包括项目切换器、任务列表/列表项/添加、控制面板状态/信息片段、
setup 浏览/运行等 HTMX 驱动的交互端点。
"""

import os
import re
from urllib.parse import quote

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse, PlainTextResponse, HTMLResponse

from loop_engineering.path_utils import resolve_project_root
from loop_engineering.server.dependencies import templates, get_agent_name
from loop_engineering.server.services.task_parser import parse_tasks, filter_tasks, tasklines_to_dicts
from loop_engineering.server.services.project_context import filter_agent_workspace_copies

router = APIRouter()


def _get_filtered_task_dicts(pr, status, filter_str, order):
    """Parse, filter, and return task dicts for template rendering."""
    tasklines = parse_tasks(pr)
    filtered = filter_tasks(tasklines, status=status, filter_name=filter_str, order=order)
    return tasklines_to_dicts(filtered)


# ── Project switcher ──

@router.get("/api/projects/switcher")
async def project_switcher(request: Request, project: str = Query(None)):
    """返回项目切换器 HTML 片段."""
    pr = resolve_project_root(project=project)
    from loop_engineering.registry import list_projects
    from loop_engineering.config import is_project_dir
    projects = list_projects()
    projects = [p for p in projects if is_project_dir(p["root"])]
    projects = filter_agent_workspace_copies(projects)

    html = '<select onchange="switchProject(this.value)" style="background: var(--bg); color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 7px; font-size: 13px; max-width: 200px;">'
    if not projects:
        html += '<option>No projects</option>'
    else:
        for p in projects:
            sel = ' selected' if p["root"] == pr else ''
            html += f'<option value="{p["root"]}"{sel}>{p["name"]}</option>'
    html += '</select>'
    html += '''<script>
        function switchProject(root) {
            var url = window.location.pathname + '?project=' + encodeURIComponent(root);
            history.pushState({}, '', url);
            htmx.ajax('GET', url, {target: '#content', swap: 'innerHTML'});
        }
    </script>'''
    return HTMLResponse(content=html)


# ── Task list fragments ──

@router.get("/tasks/list")
async def tasks_list(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _get_filtered_task_dicts(pr, status, filter, order)
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


@router.get("/tasks/list-items")
async def tasks_list_items(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _get_filtered_task_dicts(pr, status, filter, order)
    return templates.TemplateResponse(request, "_tasks_items.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


@router.post("/tasks/add")
async def tasks_add(request: Request, description: str = Form(...), assignee: str = Form(...), task_id: str = Form(""), project: str = Form(None), order: str = Form("desc"), status: str = Form("pending,in_progress"), filter: str = Form("")):
    pr = resolve_project_root(project=project, request=request)
    tp = os.path.join(pr, "tasks.md")
    from loop_engineering.task_id import generate_task_id
    tid = task_id if task_id and re.match(r'^[a-f0-9]{8}$', task_id) else generate_task_id(description)
    line = f"- [ ] {description} (→ {assignee}) [{tid}]\n"
    if os.path.exists(tp):
        with open(tp, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# Tasks\n\n")
            f.write(line)
    tasks = _get_filtered_task_dicts(pr, status, filter, order)
    resp = templates.TemplateResponse(request, "_tasks_items.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })
    resp.headers["HX-Trigger-After-Swap"] = "taskAdded"
    return resp


# ── Control panel fragments ──

@router.get("/control/status-fragment")
async def control_status_fragment(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return templates.TemplateResponse(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


@router.get("/control/info-fragment")
async def control_info_fragment(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return templates.TemplateResponse(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


# ── Setup fragments ──

@router.post("/setup/run")
async def setup_run(request: Request, project_root: str = Form(...), agent_workspace: str = Form(...),
                    agent_name: str = Form(""), type: str = Form("generic"), data_repo_path: str = Form(""),
                    port: int = Form(8080)):
    """执行 setup 流程."""
    from loop_engineering.setup import run_setup
    from loop_engineering.config import get_agent_dir
    from loop_engineering.presets import apply_preset

    config = {
        "project": {"name": os.path.basename(project_root), "root": project_root},
        "agent": {"workspace": agent_workspace, "name": agent_name, "mcp_port": 9080},
        "main": {"mcp_port": port},
    }
    if data_repo_path:
        config["data_repo"] = {"path": data_repo_path}
    config = apply_preset(config, type)
    run_setup(config)
    return RedirectResponse("/?project=" + quote(project_root), status_code=303)


@router.get("/api/setup/browse")
async def setup_browse(request: Request):
    """打开文件夹选择对话框（Windows: PowerShell, macOS: AppleScript）."""
    import platform, subprocess as sp
    if platform.system() == "Windows":
        ps = (
            'Add-Type -AssemblyName System.Windows.Forms;'
            '$f = New-Object System.Windows.Forms.FolderBrowserDialog;'
            '$f.Description = "Select project root folder";'
            'if ($f.ShowDialog() -eq "OK") { $f.SelectedPath } else { "" }'
        )
        r = sp.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
        path = r.stdout.strip()
    else:
        script = 'tell app "System Events" to return POSIX path of (choose folder)'
        r = sp.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
        path = r.stdout.strip()
    return PlainTextResponse(content=path)


@router.get("/api/setup/pickfolder")
async def setup_pickfolder(request: Request, current: str = Query("")):
    """Pick folder via keyboard input (为 Alpine 组件提供的别名)."""
    return await setup_browse(request)
