"""控制信号 API."""

import os
from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    # 回退：env 或 cwd，但排除明显错误的系统目录
    root = os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())
    # Windows 上如果跑到了 System32，说明 project 没传过来
    system_root = os.environ.get("SystemRoot", "")
    if system_root and root.startswith(system_root):
        raise RuntimeError(
            f"Project root resolved to system directory '{root}'. "
            "Please pass ?project=<path> in the URL or set LOOP_PROJECT_ROOT."
        )
    return root


class ThrottleRequest(BaseModel):
    interval: str  # e.g. "2m", "30s", "5m"


@router.get("/status")
def get_status(project: str = Query(None)):
    from loop_engineering.control import get_status as ctrl_status
    return ctrl_status(_project_root(project))


@router.post("/pause")
def pause(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(_project_root(project), True)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.delete("/pause")
def resume(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(_project_root(project), False)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.put("/throttle")
def set_throttle(req: ThrottleRequest, project: str = Query(None)):
    from loop_engineering.control import set_throttle as ctrl_set
    ctrl_set(_project_root(project), req.interval)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=f"<span style='color:var(--pass);font-size:13px;'>间隔设为 {req.interval}</span>")


@router.post("/start")
def start(project: str = Query(None)):
    from loop_engineering.control import start_loop
    result = start_loop(_project_root(project))
    if result.get("started"):
        return Response(status_code=200, headers={"HX-Refresh": "true"})
    return Response(
        status_code=200,
        headers={"HX-Refresh": "true"},
        content=f"<div class='card' style='border-color:var(--fail);background:var(--fail-bg);'><p>{result.get('reason','Failed')}</p></div>",
        media_type="text/html",
    )


@router.post("/stop")
def stop(project: str = Query(None)):
    from loop_engineering.control import stop_loop
    result = stop_loop(_project_root(project))
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.post("/focus")
def focus_window(project: str = Query(None)):
    """激活 Loop 终端窗口."""
    import platform
    if platform.system() != "Windows":
        return Response(status_code=200, content="Not Windows", media_type="text/plain")

    pr = _project_root(project)
    project_name = os.path.basename(pr)
    title = f"Loop: {project_name}"

    import subprocess
    ps = (
        f'$ws = New-Object -ComObject WScript.Shell;'
        f'$ws.AppActivate(\'{title}\');'
        f'if (-not $?) {{ exit 1 }}'
    )
    code = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, timeout=10
    ).returncode

    if code != 0:
        return Response(status_code=200, content=f"Window '{title}' not found", media_type="text/plain")
    return Response(status_code=200, content="OK", media_type="text/plain")
