"""Loop Engineering Dashboard — FastAPI 应用."""

import os
import re
import webbrowser
import subprocess

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import RedirectResponse
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


def _read_tasks(pr):
    tp = os.path.join(pr, "tasks.md")
    if not os.path.exists(tp):
        return []
    result = []
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r'^- \[(.)\]\s+(.+?)(\s+\(→\s*(\w+)\))?(\s+—\s+(.+))?$', line)
            if not m:
                continue
            s = {" ": "pending", "~": "in_progress", "x": "done"}
            result.append({
                "description": m.group(2).strip(),
                "status": s.get(m.group(1), "pending"),
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

        # branches
        branches_list = []
        try:
            r = subprocess.run("git branch -r", shell=True, capture_output=True, text=True, cwd=pr, timeout=5)
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if "agent/" not in line:
                    continue
                b = line.replace("origin/", "")
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
            },
            "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
            "branches": branches_list,
        })

    return result


# ── API routes ──
from .api import control, projects, tasks, runs, branches  # noqa: E402
app.include_router(control.router, prefix="/api/control", tags=["control"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(branches.router, prefix="/api/branches", tags=["branches"])


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
            htmx.ajax('GET', url, {target: '#content', swap: 'outerHTML'});
            history.pushState({}, '', url);
        }
    </script>'''
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


# ── Page routes ──

@app.get("/")
async def dashboard(request: Request, project: str = Query(None)):
    pr = _project_root(q=project)
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
    return _render(request, "tasks.html", {
        "request": request,
        "tasks": _read_tasks(pr),
        "agent_name": _agent_name(pr),
        "current_root": pr,
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


@app.get("/setup")
async def setup_page(request: Request):
    return _render(request, "setup.html", {"request": request})


@app.post("/setup/run")
async def setup_run(request: Request, project_root: str = Form(...), agent_name: str = Form(None), type: str = Form("")):
    from loop_engineering.registry import register_project

    if not os.path.isdir(project_root):
        return _render(request, "setup.html", {
            "request": request,
            "error": f"目录不存在: {project_root}",
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
    if type:
        from loop_engineering.presets import apply_preset
        config = apply_preset(config, type)

    try:
        from loop_engineering.setup import run_setup
        run_setup(config, force=True)
        register_project(project_root, config["project"]["name"])
        return RedirectResponse(f"/?project={project_root}", status_code=303)
    except Exception as e:
        return _render(request, "setup.html", {
            "request": request,
            "error": str(e),
        })


@app.get("/api/setup/browse")
async def browse_dirs(path: str = ""):
    """浏览目录结构."""


@app.get("/api/setup/pickfolder")
async def pick_folder():
    """打开操作系统原生文件夹选择器."""
    import platform as _plat
    if _plat.system() != "Windows":
        return {"path": ""}

    # 用 tkinter（Windows Python 自带）+ 临时脚本文件，确保有独立窗口
    import tempfile
    tmp = tempfile.mktemp(suffix=".py")
    out = tempfile.mktemp(suffix=".txt")
    with open(tmp, "w") as f:
        f.write("""
import tkinter.filedialog, tkinter
root = tkinter.Tk()
root.withdraw()
path = tkinter.filedialog.askdirectory(title="Select Folder")
with open(__import__('sys').argv[1], "w") as f:
    f.write(path or "")
""")
    try:
        subprocess.run(
            f'start "Picker" /WAIT python "{tmp}" "{out}"',
            shell=True, timeout=120
        )
        if os.path.exists(out):
            with open(out) as f:
                path = f.read().strip()
            os.remove(out)
        else:
            path = ""
    except Exception:
        path = ""
    finally:
        try:
            os.remove(tmp)
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
