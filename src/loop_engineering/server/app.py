"""Loop Engineering Dashboard — FastAPI 应用."""

import os
from fastapi import FastAPI

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

# ── Page routes (full pages, wrapped in base.html) ──
from .routers import pages  # noqa: E402
app.include_router(pages.router)

# ── HTMX fragment routes (partials for dynamic updates) ──
from .routers import fragments  # noqa: E402
app.include_router(fragments.router)


# ── Startup ──

def start_server(project_root, port=8765, open_browser=True):
    os.environ["LOOP_PROJECT_ROOT"] = project_root

    # Register current project on first launch
    from loop_engineering.registry import register_project
    register_project(project_root)

    import webbrowser
    import uvicorn
    if open_browser:
        webbrowser.open(f"http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
