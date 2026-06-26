"""Loop Engineering Dashboard — FastAPI 应用."""

import os
import re
import webbrowser
from urllib.parse import quote
import subprocess

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import RedirectResponse, Response

from loop_engineering.path_utils import resolve_project_root
from loop_engineering.server.dependencies import templates, is_htmx, render_page, get_agent_name
from loop_engineering.server.services.task_parser import parse_tasks, filter_tasks
from loop_engineering.server.services.project_context import build_projects_context

app = FastAPI(title="Loop Engineering Dashboard")


# ── API routes ──
from .api import control, projects, tasks, runs, branches, config, docs  # noqa: E402
app.include_router(control.router, prefix="/api/control", tags=["control"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(branches.router, prefix="/api/branches", tags=["branches"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(docs.router, prefix="/api/docs", tags=["docs"])


def _read_tasks_dict(pr):
    """读取 tasks.md 并返回 dict 列表（用于现有模板兼容）。"""
    tasklines = parse_tasks(pr)
    result = []
    for tl in tasklines:
        status = tl.status
        s = {" ": "pending", "~": "in_progress", "x": "done", "r": "reopen"}
        desc = tl.description
        if tl.task_id:
            desc = re.sub(r'\s+\[[a-f0-9]{8}\]\s*$', '', desc).strip()
        result.append({
            "description": desc,
            "task_id": tl.task_id,
            "status": s.get(status, "pending"),
            "assignee": tl.assignee,
            "meta": tl.meta,
            "feedback": tl.feedback,
        })
    return result


def _filter_agent_workspace_copies(project_list):
    """过滤掉 agent workspace 拷贝."""
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


def _apply_task_filters(tasks_list, status_str, filter_str, order_str):
    """Apply status/filter/order to a task dict list."""
    allowed = [s.strip() for s in status_str.split(",") if s.strip()]
    if "in_progress" in allowed:
        allowed.extend(["pending_merge", "reopen"])
    if "done" in allowed:
        allowed.append("pending_merge")
    tasks = [t for t in tasks_list if t["status"] in allowed]
    if filter_str:
        f_lower = filter_str.strip().lower()
        tasks = [t for t in tasks if t.get("assignee", "").lower() == f_lower]
    if order_str == "desc":
        tasks = list(reversed(tasks))
    return tasks


@app.get("/api/projects/switcher")
async def project_switcher(request: Request, project: str = Query(None)):
    """返回项目切换器 HTML 片段."""
    pr = resolve_project_root(project=project)
    from loop_engineering.registry import list_projects
    from loop_engineering.config import is_project_dir
    projects = list_projects()
    projects = [p for p in projects if is_project_dir(p["root"])]
    projects = _filter_agent_workspace_copies(projects)

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
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


# ── Page routes ──

@app.get("/")
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


@app.get("/tasks")
async def tasks_page(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _apply_task_filters(_read_tasks_dict(pr), status, filter, order)
    return render_page(request, "tasks.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "current_root": pr,
        "order": order,
        "status": status,
        "filter": filter,
    })


@app.get("/tasks/list")
async def tasks_list(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _apply_task_filters(_read_tasks_dict(pr), status, filter, order)
    from fastapi.templating import Jinja2Templates
    import os as _os
    _td = _os.path.join(_os.path.dirname(__file__), "templates")
    _tpl = Jinja2Templates(directory=_td)
    return _tpl.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


@app.get("/tasks/list-items")
async def tasks_list_items(request: Request, project: str = Query(None), order: str = Query("desc"), status: str = Query("pending,in_progress"), filter: str = Query("")):
    pr = resolve_project_root(project=project, request=request)
    tasks = _apply_task_filters(_read_tasks_dict(pr), status, filter, order)
    from fastapi.templating import Jinja2Templates
    import os as _os
    _td = _os.path.join(_os.path.dirname(__file__), "templates")
    _tpl = Jinja2Templates(directory=_td)
    return _tpl.TemplateResponse(request, "_tasks_items.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


@app.post("/tasks/add")
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
    tasks = _apply_task_filters(_read_tasks_dict(pr), status, filter, order)
    from fastapi.templating import Jinja2Templates
    import os as _os
    _td = _os.path.join(_os.path.dirname(__file__), "templates")
    _tpl = Jinja2Templates(directory=_td)
    resp = _tpl.TemplateResponse(request, "_tasks_items.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })
    resp.headers["HX-Trigger-After-Swap"] = "taskAdded"
    return resp


@app.get("/runs")
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


@app.get("/control")
async def control_page(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return render_page(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


@app.get("/control/status-fragment")
async def control_status_fragment(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return templates.TemplateResponse(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


@app.get("/control/info-fragment")
async def control_info_fragment(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return templates.TemplateResponse(request, "control.html", {
        "request": request,
        "current_root": pr,
    })


@app.get("/settings")
async def settings_page(request: Request, project: str = Query(None)):
    pr = resolve_project_root(project=project, request=request)
    return render_page(request, "settings.html", {
        "request": request,
        "current_root": pr,
    })


@app.get("/setup")
async def setup_page(request: Request, project: str = Query(None)):
    """Setup wizard — always served standalone (no base.html wrapping)."""
    from fastapi.templating import Jinja2Templates
    import os as _os
    _td = _os.path.join(_os.path.dirname(__file__), "templates")
    _tpl = Jinja2Templates(directory=_td)
    pr = resolve_project_root(project=project)
    from loop_engineering.config import detect_config
    detected = detect_config(pr)
    return _tpl.TemplateResponse(request, "setup.html", {
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


@app.post("/setup/run")
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


@app.get("/api/setup/browse")
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
        # macOS: use AppleScript
        script = 'tell app "System Events" to return POSIX path of (choose folder)'
        r = sp.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
        path = r.stdout.strip()
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=path)


@app.get("/api/setup/pickfolder")
async def setup_pickfolder(request: Request, current: str = Query("")):
    """Pick folder via keyboard input (为 Alpine 组件提供的别名)."""
    return await setup_browse(request)


def start_server(project_root, port=8080, open_browser=True):
    """启动 Dashboard 服务器."""
    import uvicorn
    os.environ["LOOP_PROJECT_ROOT"] = os.path.abspath(project_root)
    if open_browser:
        webbrowser.open(f"http://localhost:{port}/?project={quote(project_root)}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
