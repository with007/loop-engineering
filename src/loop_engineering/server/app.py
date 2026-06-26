"""Loop Engineering Dashboard — FastAPI 应用.

路由全部在 routers/ 和 api/ 下，app.py 仅负责实例创建、注册和启动。
"""

import os
import webbrowser
from urllib.parse import quote

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

# ── Page & fragment routes ──
from .routers import pages, fragments  # noqa: E402
app.include_router(pages.router)
app.include_router(fragments.router)


def start_server(project_root, port=8080, open_browser=True):
    """启动 Dashboard 服务器."""
    import uvicorn
    os.environ["LOOP_PROJECT_ROOT"] = os.path.abspath(project_root)
    if open_browser:
        webbrowser.open(f"http://localhost:{port}/?project={quote(project_root)}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
