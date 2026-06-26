"""HTMX fragment routes — partial responses for dynamic page updates."""

import os
import re
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, Response

from ..dependencies import get_project_root, get_agent_name, templates, render
from ..services.task_parser import parse_tasks, filter_tasks

router = APIRouter()


# ── Control fragments ──

@router.get("/control/status-fragment")
async def control_status_fragment(request: Request, project: str = Query(None)):
    """Control page loop status + buttons fragment (5s polling)."""
    from loop_engineering.control import get_status

    pr = get_project_root(request, q=project)
    status = get_status(pr)
    is_running = status.get("running", False)
    paused = status.get("paused", False)
    html = f'''<div id="control-status" hx-get="/control/status-fragment" hx-trigger="every 5s" hx-swap="outerHTML">
        <div class="card" style="margin-bottom: 20px;">
            <div class="status-indicator" style="margin-bottom: 16px;">
                <span class="status-dot {"active" if is_running else ("paused" if paused else "")}"></span>
                <span style="font-weight: 600; font-size: 18px;">
                    {"Loop 运行中" if is_running else ("已暂停" if paused else "空闲")}
                </span>
                <span style="color: var(--dim); font-size: 13px; margin-left: auto;">
                    {f'HB: <span id="hb-time" data-iso="{status["heartbeat"]}">{status["heartbeat"][:19].replace("T", " ")}</span>' if status.get("heartbeat") else "无心跳"}
                </span>
            </div>
            <div class="controls" style="margin-bottom: 16px;">'''
    if is_running:
        html += '''<button class="btn btn-danger"
                        hx-post="/api/control/stop"
                        hx-target="#control-status"
                        hx-swap="outerHTML">停止 Loop</button>
                <button class="btn btn-sm"
                        hx-post="/api/control/focus"
                        hx-swap="none"
                        style="background: var(--surface2); color: var(--text); border: 1px solid var(--border);">🔍 聚焦窗口</button>'''
        if paused:
            html += '''<button class="btn btn-primary"
                        hx-delete="/api/control/pause"
                        hx-target="#control-status"
                        hx-swap="outerHTML">恢复</button>'''
        else:
            html += '''<button class="btn btn-warn"
                        hx-post="/api/control/pause"
                        hx-target="#control-status"
                        hx-swap="outerHTML">暂停</button>'''
    else:
        html += '''<button class="btn btn-success"
                        hx-post="/api/control/start"
                        hx-target="#control-status"
                        hx-swap="outerHTML">启动 Loop</button>'''
        if status.get("pid") and status.get("pid_alive"):
            html += '''<button class="btn btn-sm"
                        hx-post="/api/control/focus"
                        hx-swap="none"
                        style="background: var(--surface2); color: var(--text); border: 1px solid var(--border); margin-left: 8px;">🔍 聚焦窗口</button>'''
    html += '''</div></div></div>
    <script>
        (function() {
            var el = document.getElementById('hb-time');
            if (!el) return;
            var iso = el.getAttribute('data-iso');
            if (!iso) return;
            var d = new Date(iso);
            var now = new Date();
            var sec = Math.floor((now - d) / 1000);
            if (sec < 60) el.textContent = sec + 's ago';
            else if (sec < 3600) el.textContent = Math.floor(sec/60) + 'm ago';
            else el.textContent = Math.floor(sec/3600) + 'h ago';
        })();
    </script>'''
    return HTMLResponse(content=html)


@router.get("/control/info-fragment")
async def control_info_fragment(request: Request, project: str = Query(None)):
    """Control page signal files + working principle fragment (5s polling)."""
    from loop_engineering.control import get_status

    pr = get_project_root(request, q=project)
    status = get_status(pr)
    is_running = status.get("running", False)
    paused = status.get("paused", False)
    hb_color = "var(--pass)" if is_running else "#64748b"
    pause_color = "var(--active)" if paused else "#64748b"
    html = f'''<div id="control-info" hx-get="/control/info-fragment" hx-trigger="every 5s" hx-swap="outerHTML">
        <div class="grid grid-2">
            <div class="card">
                <h3>信号文件</h3>
                <div style="display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-family: monospace;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>control/heartbeat</span>
                        <span style="color: {hb_color}">{status.get("heartbeat") or "无"}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>control/pause</span>
                        <span style="color: {pause_color}">{"ON" if paused else "关"}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>control/throttle</span>
                        <span style="color: var(--dim);">{status.get("throttle", "")}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>control/loop.pid</span>
                        <span style="color: var(--dim);">{status.get("pid") or "无"}</span>
                    </div>
                </div>
            </div>
            <div class="card">
                <h3>工作原理</h3>
                <p style="color: var(--muted); font-size: 13px; line-height: 1.6;">
                    <strong>Start</strong> 打开终端窗口运行<br>
                    <code style="color: var(--blue);">claude --dangerously-skip-permissions -p '/runloop'</code>
                </p>
                <p style="color: var(--muted); font-size: 13px; line-height: 1.6; margin-top: 8px;">
                    Dashboard 通过以下方式检测 Loop 状态：<br>
                    • 心跳文件（每轮更新）<br>
                    • 进程 ID（终端窗口存活）
                </p>
            </div>
        </div>
    </div>'''
    return HTMLResponse(content=html)


# ── Task list fragments ──

@router.get("/tasks/list")
async def tasks_list(
    request: Request,
    project: str = Query(None),
    order: str = Query("desc"),
    status: str = Query("pending,in_progress"),
    filter: str = Query(""),
):
    """Return full task area (controls + list) for control operation refresh."""
    pr = get_project_root(request, q=project)
    tasks = parse_tasks(pr)
    tasks = filter_tasks(tasks, status=status, order=order, filter_name=filter)
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


@router.get("/tasks/list-items")
async def tasks_list_items(
    request: Request,
    project: str = Query(None),
    order: str = Query("desc"),
    status: str = Query("pending,in_progress"),
    filter: str = Query(""),
):
    """Return task items only (progress bar + cards) for 30s polling."""
    pr = get_project_root(request, q=project)
    tasks = parse_tasks(pr)
    tasks = filter_tasks(tasks, status=status, order=order, filter_name=filter)
    return templates.TemplateResponse(request, "_tasks_items.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


# ── Task add (form submission) ──

@router.post("/tasks/add")
async def tasks_add(
    request: Request,
    description: str = Form(...),
    assignee: str = Form(...),
    task_id: str = Form(""),
    project: str = Form(None),
    order: str = Form("desc"),
    status: str = Form("pending,in_progress"),
    filter: str = Form(""),
):
    pr = get_project_root(request, q=project)
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
    tasks = parse_tasks(pr)
    tasks = filter_tasks(tasks, status=status, order=order, filter_name=filter)
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": tasks,
        "agent_name": get_agent_name(pr),
        "order": order,
        "status": status,
        "filter": filter,
    })


# ── Setup fragments ──

@router.post("/setup/run")
async def setup_run(
    request: Request,
    project_root: str = Form(...),
    agent_name: str = Form(None),
    agent_workspace: str = Form(None),
    main_port: int = Form(8080),
    agent_port: int = Form(9080),
    type: str = Form(""),
):
    import subprocess
    from loop_engineering.registry import register_project

    if not os.path.isdir(project_root):
        return render(request, "setup.html", {
            "request": request,
            "error": f"目录不存在: {project_root}",
        })

    if not os.path.isdir(os.path.join(project_root, ".git")):
        return render(request, "setup.html", {
            "request": request,
            "error": f"不是 Git 仓库: {project_root}\n请先用 git init 或 git clone 初始化项目",
        })

    # Determine agent name
    if not agent_name:
        try:
            r = subprocess.run(
                "git config user.name", shell=True, capture_output=True, text=True,
                encoding='utf-8', errors='replace', cwd=project_root, timeout=5
            )
            agent_name = r.stdout.strip()
        except Exception:
            agent_name = ""

    # Build config
    from loop_engineering.config import detect_config
    config = detect_config(project_root)
    config["agent"]["name"] = agent_name or config["agent"].get("name", "")
    if agent_workspace:
        config["agent"]["workspace"] = os.path.abspath(agent_workspace)
    config["main"]["mcp_port"] = main_port
    config["agent"]["mcp_port"] = agent_port
    if type:
        from loop_engineering.presets import apply_preset
        config = apply_preset(config, type)

    try:
        from loop_engineering.setup import run_setup
        run_setup(config, force=True)
        register_project(project_root, config["project"]["name"])
        return Response(status_code=200, headers={"HX-Redirect": f"/?project={quote(project_root)}"})
    except Exception as e:
        return render(request, "setup.html", {
            "request": request,
            "error": str(e),
        })


# ── Project switcher / setup helpers ──

@router.get("/api/projects/switcher")
async def project_switcher(request: Request, project: str = Query(None)):
    """Return project switcher HTML fragment."""
    pr = get_project_root(q=project)
    from loop_engineering.registry import list_projects
    from loop_engineering.config import is_project_dir
    from ..services.project_context import _filter_agent_workspace_copies

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
            htmx.ajax('GET', url, {target: '#content', swap: 'innerHTML'});
            history.pushState({}, '', url);
        }
    </script>'''
    return HTMLResponse(content=html)


@router.get("/api/setup/browse")
async def browse_dirs(path: str = ""):
    """Browse directory structure."""
    import platform as _plat
    if not path or not os.path.exists(path):
        if _plat.system() == "Windows":
            import string
            drives = []
            for d in string.ascii_uppercase:
                dp = f"{d}:/"
                if os.path.exists(dp):
                    drives.append({"name": dp, "path": dp, "is_drive": True})
            return {"path": "", "entries": drives}
        else:
            path = "/"
    entries = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith("."):
                entries.append({"name": name, "path": full.replace("\\", "/"), "is_dir": True})
    except PermissionError:
        pass
    parent = os.path.dirname(path).replace("\\", "/")
    if parent == path:
        parent = ""
    return {"path": path.replace("\\", "/"), "parent": parent, "entries": entries}


@router.get("/api/setup/pickfolder")
async def pick_folder():
    """VBS COM native folder picker."""
    import platform as _plat
    import tempfile
    import time as _time
    import subprocess

    if _plat.system() != "Windows":
        return {"path": ""}

    vbs = tempfile.mktemp(suffix=".vbs")
    out = tempfile.mktemp(suffix=".txt")
    with open(vbs, "w") as f:
        f.write(f"""
Set objShell = CreateObject("Shell.Application")
Set objFolder = objShell.BrowseForFolder(0, "Select Folder", 0, 0)
Set fso = CreateObject("Scripting.FileSystemObject")
Set out = fso.CreateTextFile("{out.replace(chr(92), chr(92)+chr(92))}", True)
If Not objFolder Is Nothing Then
    out.Write objFolder.Self.Path
End If
out.Close
""")
    try:
        subprocess.run(
            ["cscript", "//Nologo", vbs],
            timeout=300
        )
        _time.sleep(0.5)
        if os.path.exists(out):
            with open(out) as f:
                path = f.read().strip()
            os.remove(out)
        else:
            path = ""
    except Exception:
        path = ""
    try:
        os.remove(vbs)
    except Exception:
        pass
    return {"path": path}
