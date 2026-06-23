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


@router.get("/log")
def get_log(project: str = Query(None), lines: int = Query(100)):
    """返回最近 N 行 loop 输出日志."""
    pr = _project_root(project)
    log_path = os.path.join(pr, ".loop-engineering", "control", "loop.log")
    if not os.path.exists(log_path):
        return Response(status_code=200, content="(no log yet)", media_type="text/plain")
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # 取最后 N 行
        all_lines = content.split("\n")
        last = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return Response(status_code=200, content="\n".join(last), media_type="text/plain")
    except Exception:
        return Response(status_code=200, content="(log read error)", media_type="text/plain")


@router.post("/focus")
def focus_window(project: str = Query(None)):
    """激活 Loop 终端窗口（通过 PID）."""
    import platform
    if platform.system() != "Windows":
        return Response(status_code=200, content="Not Windows", media_type="text/plain")

    pr = _project_root(project)
    from loop_engineering.control import _read_pid, _pid_alive, _pid_path
    pid = _read_pid(pr)
    if not pid or not _pid_alive(pid):
        return Response(status_code=200, content="Loop not running", media_type="text/plain")

    import subprocess
    ps = (
        f'Add-Type -Name WinAPI -Namespace Temp -MemberDefinition \''
        f'[DllImport("kernel32.dll")]public static extern bool FreeConsole();'
        f'[DllImport("kernel32.dll")]public static extern bool AttachConsole(uint dwProcessId);'
        f'[DllImport("kernel32.dll")]public static extern IntPtr GetConsoleWindow();'
        f'[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr hWnd);'
        f'[DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr hWnd,int nCmdShow);'
        f'\';'
        f'[Temp.WinAPI]::FreeConsole()|Out-Null;'
        f'$ok=[Temp.WinAPI]::AttachConsole({pid});'
        f'if(-not $ok){{Write-Error "AttachConsole failed";exit 1}};'
        f'$hwnd=[Temp.WinAPI]::GetConsoleWindow();'
        f'[Temp.WinAPI]::ShowWindow($hwnd,9)|Out-Null;'
        f'[Temp.WinAPI]::SetForegroundWindow($hwnd)|Out-Null;'
        f'[Temp.WinAPI]::FreeConsole()|Out-Null;'
        f'$null = [Temp.WinAPI]::AttachConsole(0xFFFFFFFF)'
    )
    code = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, timeout=10
    ).returncode

    if code != 0:
        return Response(status_code=200, content=f"Cannot focus PID {pid}", media_type="text/plain")
    return Response(status_code=200, content="OK", media_type="text/plain")
