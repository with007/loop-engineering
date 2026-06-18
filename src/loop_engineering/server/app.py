"""Loop Engineering Dashboard — FastAPI 应用."""

import os
import re
import webbrowser
import subprocess

from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Loop Engineering Dashboard")

_tpl_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_tpl_dir)

# API 路由
from .api import control, projects, tasks, runs, branches  # noqa: E402

app.include_router(control.router, prefix="/api/control", tags=["control"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(branches.router, prefix="/api/branches", tags=["branches"])


def _project_root():
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


def _read_tasks():
    pr = _project_root()
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


def _agent_name():
    from loop_engineering.config import read_config
    cfg = read_config(_project_root())
    return cfg.get("agent", {}).get("name", "")


# ── 页面路由 ──


@app.get("/")
async def dashboard(request: Request):
    from loop_engineering.config import read_config
    from loop_engineering.runlog import get_pass_rate
    pr = _project_root()
    cfg = read_config(pr)
    name = cfg.get("project", {}).get("name", os.path.basename(pr))

    tasks_list = _read_tasks()
    pending = sum(1 for t in tasks_list if t["status"] == "pending")
    active = sum(1 for t in tasks_list if t["status"] == "in_progress")
    done = sum(1 for t in tasks_list if t["status"] == "done")
    passed, total, rate = get_pass_rate(pr, days=7)

    # count agent branches
    try:
        r = subprocess.run("git branch -r", shell=True, capture_output=True, text=True, cwd=pr, timeout=10)
        branch_count = sum(1 for l in r.stdout.split("\n") if "agent/" in l)
    except Exception:
        branch_count = 0

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "projects": [{
            "name": name,
            "root": pr,
            "tasks": {"pending": pending, "in_progress": active, "done": done},
            "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
            "unmerged_branches": branch_count,
        }]
    })


@app.get("/tasks")
async def tasks_page(request: Request):
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "tasks": _read_tasks(),
        "agent_name": _agent_name(),
    })


@app.post("/tasks/add")
async def tasks_add(request: Request, description: str = Form(...), assignee: str = Form(...)):
    pr = _project_root()
    tp = os.path.join(pr, "tasks.md")
    line = f"- [ ] {description} (→ {assignee})\n"
    if os.path.exists(tp):
        with open(tp, "a", encoding="utf-8") as f:
            f.write(line)
    else:
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# Tasks\n\n")
            f.write(line)
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "tasks": _read_tasks(),
        "agent_name": _agent_name(),
    })


@app.get("/runs")
async def runs_page(request: Request, whoami: str = ""):
    from loop_engineering.runlog import list_runs, get_pass_rate
    pr = _project_root()
    entries = list_runs(pr, whoami=whoami or None, limit=100)
    passed, total, rate = get_pass_rate(pr, days=7)

    # collect distinct agents
    agents = list(set(e.get("whoami", "") for e in entries if e.get("whoami")))

    return templates.TemplateResponse("runs.html", {
        "request": request,
        "runs": entries,
        "pass_rate": {"passed": passed, "total": total, "rate": round(rate * 100, 1)},
        "agents": agents,
        "filter_whoami": whoami,
    })


@app.get("/branches")
async def branches_page(request: Request):
    pr = _project_root()
    branches_list = []
    try:
        r = subprocess.run("git branch -r", shell=True, capture_output=True, text=True, cwd=pr, timeout=10)
        for line in r.stdout.strip().split("\n"):
            line = line.strip()
            if "agent/" not in line:
                continue
            b = line.replace("origin/", "")
            # check merged
            r2 = subprocess.run(
                f"git merge-base --is-ancestor origin/{b} origin/master",
                shell=True, capture_output=True, cwd=pr, timeout=10
            )
            branches_list.append({"name": b, "merged": r2.returncode == 0})
    except Exception:
        pass

    return templates.TemplateResponse("branches.html", {
        "request": request,
        "branches": branches_list,
    })


@app.get("/control")
async def control_page(request: Request):
    from loop_engineering.control import get_status
    return templates.TemplateResponse("control.html", {
        "request": request,
        "status": get_status(_project_root()),
    })


def start_server(project_root, port=8765, open_browser=True):
    os.environ["LOOP_PROJECT_ROOT"] = project_root
    import uvicorn
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
