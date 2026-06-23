"""Loop Engineering Dashboard — FastAPI 应用."""

import os
import re
import webbrowser
from urllib.parse import quote
import subprocess

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Loop Engineering Dashboard")

_tpl_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_tpl_dir)
templates.env.cache = None


def _project_root(request: Request = None, q: str = None):
    """获取当前项目根目录。优先 query param，否则 env var."""
    if q:
        return q
    if request:
        q = request.query_params.get("project")
        if q:
            return q
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


def _task_id_of(description):
    """从描述生成 task_id（与 task_pick.py slugify 逻辑一致）."""
    import hashlib
    desc = re.split(r'\s+—\s+', description.strip())[0].strip().replace(' ', '-').lower()
    result = re.sub(r'[^a-z0-9-]', '', desc)
    result = re.sub(r'^-+|-+$', '', result)
    if len(result) < 3:
        result = 'task-' + hashlib.md5(desc.encode('utf-8')).hexdigest()[:8]
    return result[:40]


def _read_tasks(pr):
    tp = os.path.join(pr, "tasks.md")
    if not os.path.exists(tp):
        return []
    # 收集已有的 agent 分支名
    agent_branches = set()
    try:
        r = subprocess.run('git branch --list "agent/*"', shell=True, capture_output=True, text=True, cwd=pr, timeout=5)
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b:
                agent_branches.add(b.split("/")[-1])  # 只取 task_id 部分
    except Exception:
        pass

    result = []
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^- \[(.)\]\s+(.+?)(\s+\(→\s*(\w+)\))?(\s+—\s+(.+))?$', line)
            if not m:
                continue
            desc = m.group(2).strip()
            tid = _task_id_of(desc)
            status_char = m.group(1)
            if status_char == "x" and tid in agent_branches:
                status = "pending_merge"
            else:
                s = {" ": "pending", "~": "in_progress", "x": "done"}
                status = s.get(status_char, "pending")
            result.append({
                "description": desc,
                "task_id": tid,
                "status": status,
                "assignee": m.group(4) or "",
                "meta": m.group(6) or "",
            })
    return result


def _agent_name(pr):
    from loop_engineering.config import read_config
    cfg = read_config(pr)
    return cfg.get("agent", {}).get("name", "")


def _is_htmx(request: Request):
    return request.headers.get("HX-Request", "") == "true"


def _render(request: Request, template_name: str, context: dict):
    if _is_htmx(request):
        return templates.TemplateResponse(request, template_name, context)
    content_html = templates.get_template(template_name).render(context)
    return templates.TemplateResponse(request, "base.html", {
        "request": request,
        "content": content_html,
    })


def _build_projects_context(request: Request, current_pr: str):
    """构建项目列表 + 当前项目信息。仅包含有 loop-config.yaml 的项目."""
    from loop_engineering.registry import list_projects, register_project
    projects = list_projects()

    # 自动注册当前项目（仅当 loop-config.yaml 存在时）
    cfg_path = os.path.join(current_pr, "loop-config.yaml")
    if os.path.exists(cfg_path) and not any(p["root"] == current_pr for p in projects):
        register_project(current_pr)
        projects = list_projects()

    # 过滤掉没有 loop-config.yaml 的孤项目
    projects = [p for p in projects if os.path.exists(os.path.join(p["root"], "loop-config.yaml"))]

    # 构建详情
    result = []
    for p in projects:
        pr = p["root"]
        cfg = {}
        from loop_engineering.config import read_config
        try:
            cfg = read_config(pr)
        except Exception:
            pass
        tasks = _read_tasks(pr)
        from loop_engineering.runlog import get_pass_rate
        passed, total, rate = get_pass_rate(pr, days=7)

        # branches — 同时查本地和远程 agent 分支
        branches_list = []
        seen = set()
        try:
            # 本地 agent 分支
            r_local = subprocess.run('git branch --list "agent/*"', shell=True, capture_output=True, text=True, cwd=pr, timeout=5)
            for line in r_local.stdout.strip().split("\n"):
                b = line.strip().lstrip("*+ ")
                if not b:
                    continue
                seen.add(b)
                # 检查是否已合入 {{ default_ref }}
                r_merged = subprocess.run(
                    f"git branch --merged master --list {b}", shell=True, capture_output=True, cwd=pr, timeout=5
                )
                branches_list.append({"name": b, "merged": r_merged.stdout.strip() != ""})
            # 远程 agent 分支
            r_remote = subprocess.run("git branch -r", shell=True, capture_output=True, text=True, cwd=pr, timeout=5)
            for line in r_remote.stdout.strip().split("\n"):
                line = line.strip()
                if "agent/" not in line:
                    continue
                b = line.replace("origin/", "")
                if b in seen:
                    continue
                r2 = subprocess.run(
                    f"git merge-base --is-ancestor origin/{b} origin/master",
                    shell=True, capture_output=True, cwd=pr, timeout=5
                )
                branches_list.append({"name": b, "merged": r2.returncode == 0})
        except Exception:
            pass

        result.append({
            "name": p["name"],
            "root": pr,
            "is_current": pr == current_pr,
            "tasks": {
                "pending": sum(1 for t in tasks if t["status"] == "pending"),
                "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
                "done": sum(1 for t in tasks if t["status"] == "done"),
                "pending_merge": sum(1 for t in tasks if t["status"] == "pending_merge"),
            },
            "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
            "branches": branches_list,
        })

    return result


# ── API routes ──
from .api import control, projects, tasks, runs, branches, config  # noqa: E402
app.include_router(control.router, prefix="/api/control", tags=["control"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(branches.router, prefix="/api/branches", tags=["branches"])
app.include_router(config.router, prefix="/api/config", tags=["config"])


@app.get("/api/projects/switcher")
async def project_switcher(request: Request, project: str = Query(None)):
    """返回项目切换器 HTML 片段."""
    pr = _project_root(q=project)
    from loop_engineering.registry import list_projects
    projects = list_projects()
    projects = [p for p in projects if os.path.exists(os.path.join(p["root"], "loop-config.yaml"))]

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
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


# ── Page routes ──

@app.get("/")
async def dashboard(request: Request, project: str = Query(None)):
    pr = _project_root(request, q=project)
    from loop_engineering.registry import list_projects

    # If current dir is not a project, fall back to a registered one
    cfg_path = os.path.join(pr, "loop-config.yaml")
    if not os.path.exists(cfg_path):
        projects = list_projects()
        # Filter to only those with loop-config.yaml
        valid = [p for p in projects if os.path.exists(os.path.join(p["root"], "loop-config.yaml"))]
        if valid:
            return RedirectResponse(f"/?project={quote(valid[0]['root'])}", status_code=303)
        else:
            return RedirectResponse("/setup", status_code=303)

    all_projects = _build_projects_context(request, pr)
    current = next((p for p in all_projects if p["is_current"]), all_projects[0] if all_projects else None)
    return _render(request, "dashboard.html", {
        "request": request,
        "projects": all_projects,
        "current_root": pr,
        "current": current,
    })


@app.get("/tasks")
async def tasks_page(request: Request, project: str = Query(None)):
    pr = _project_root(request, q=project)
    return _render(request, "tasks.html", {
        "request": request,
        "tasks": _read_tasks(pr),
        "agent_name": _agent_name(pr),
        "current_root": pr,
    })


@app.get("/tasks/list")
async def tasks_list(request: Request, project: str = Query(None)):
    """返回仅任务列表的局部片段（供 polling 和表单提交后刷新）."""
    pr = _project_root(request, q=project)
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": _read_tasks(pr),
        "agent_name": _agent_name(pr),
    })


@app.post("/tasks/add")
async def tasks_add(request: Request, description: str = Form(...), assignee: str = Form(...), project: str = Form(None)):
    pr = _project_root(request, q=project)
    tp = os.path.join(pr, "tasks.md")
    line = f"- [ ] {description} (→ {assignee})\n"
    if os.path.exists(tp):
        with open(tp, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# Tasks\n\n")
            f.write(line)
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "request": request,
        "tasks": _read_tasks(pr),
        "agent_name": _agent_name(pr),
    })


@app.get("/runs")
async def runs_page(request: Request, whoami: str = "", project: str = Query(None)):
    from loop_engineering.runlog import list_runs, get_pass_rate
    pr = _project_root(request, q=project)
    entries = list_runs(pr, whoami=whoami or None, limit=100)
    passed, total, rate = get_pass_rate(pr, days=7)
    agents = list(set(e.get("whoami", "") for e in entries if e.get("whoami")))
    return _render(request, "runs.html", {
        "request": request,
        "runs": entries,
        "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
        "agents": agents,
        "filter_whoami": whoami,
        "current_root": pr,
    })


@app.get("/control")
async def control_page(request: Request, project: str = Query(None)):
    from loop_engineering.control import get_status
    pr = _project_root(request, q=project)
    return _render(request, "control.html", {
        "request": request,
        "status": get_status(pr),
        "current_root": pr,
    })


@app.get("/control/status-fragment")
async def control_status_fragment(request: Request, project: str = Query(None)):
    """Control 页的 Loop 状态 + 按钮片段（供 5s polling 刷新）."""
    from loop_engineering.control import get_status
    pr = _project_root(request, q=project)
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
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@app.get("/control/info-fragment")
async def control_info_fragment(request: Request, project: str = Query(None)):
    """Control 页的信号文件 + 工作原理片段（供 5s polling 刷新）."""
    from loop_engineering.control import get_status
    pr = _project_root(request, q=project)
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
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@app.get("/settings")
async def settings_page(request: Request, project: str = Query(None)):
    from loop_engineering.config import read_config
    from loop_engineering.presets import list_presets

    pr = _project_root(request, q=project)
    cfg_path = os.path.join(pr, "loop-config.yaml")
    if not os.path.exists(cfg_path):
        return RedirectResponse("/setup", status_code=303)

    cfg = read_config(pr)
    presets = [{"key": k, "name": n, "desc": d} for k, n, d in list_presets()]

    return _render(request, "settings.html", {
        "request": request,
        "current_root": pr,
        "config": cfg,
        "presets": presets,
    })


@app.get("/setup")
async def setup_page(request: Request):
    import subprocess
    git_user = ""
    try:
        r = subprocess.run("git config user.name", shell=True, capture_output=True, text=True, timeout=5)
        git_user = r.stdout.strip()
    except Exception:
        pass
    return _render(request, "setup.html", {"request": request, "git_user": git_user})


@app.post("/setup/run")
async def setup_run(request: Request, project_root: str = Form(...), agent_name: str = Form(None),
                    agent_workspace: str = Form(None), main_port: int = Form(8080),
                    agent_port: int = Form(9080), type: str = Form("")):
    from loop_engineering.registry import register_project

    if not os.path.isdir(project_root):
        return _render(request, "setup.html", {
            "request": request,
            "error": f"目录不存在: {project_root}",
        })

    if not os.path.isdir(os.path.join(project_root, ".git")):
        return _render(request, "setup.html", {
            "request": request,
            "error": f"不是 Git 仓库: {project_root}\n请先用 git init 或 git clone 初始化项目",
        })

    # 确定 agent name
    if not agent_name:
        try:
            r = subprocess.run("git config user.name", shell=True, capture_output=True, text=True, cwd=project_root, timeout=5)
            agent_name = r.stdout.strip()
        except Exception:
            agent_name = ""

    # 构建配置
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
        return _render(request, "setup.html", {
            "request": request,
            "error": str(e),
        })


@app.get("/api/setup/browse")
async def browse_dirs(path: str = ""):
    """浏览目录结构."""
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


@app.get("/api/setup/pickfolder")
async def pick_folder():
    """VBS COM 原生文件夹选择器."""
    import platform as _plat, tempfile, time as _time
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
        # 不捕获输出，让 cscript 正常显示对话框
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


# ── Startup ──

def start_server(project_root, port=8765, open_browser=True):
    os.environ["LOOP_PROJECT_ROOT"] = project_root

    # 首次启动时注册当前项目
    from loop_engineering.registry import register_project
    register_project(project_root)

    import uvicorn
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
