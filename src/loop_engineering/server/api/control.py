"""控制信号 API."""

import os
from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel
from loop_engineering.path_utils import resolve_project_root, resolve_control_root

router = APIRouter()


class ThrottleRequest(BaseModel):
    interval: str  # e.g. "2m", "30s", "5m"


@router.get("/status")
def get_status(project: str = Query(None)):
    from loop_engineering.control import get_status as ctrl_status
    return ctrl_status(resolve_control_root(resolve_project_root(project=project)))


@router.post("/pause")
def pause(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(resolve_control_root(resolve_project_root(project=project)), True)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.delete("/pause")
def resume(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(resolve_control_root(resolve_project_root(project=project)), False)
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.put("/throttle")
def set_throttle(req: ThrottleRequest, project: str = Query(None)):
    from loop_engineering.control import set_throttle as ctrl_set
    ctrl_set(resolve_control_root(resolve_project_root(project=project)), req.interval)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=f"<span style='color:var(--pass);font-size:13px;'>间隔设为 {req.interval}</span>")


@router.post("/start")
def start(project: str = Query(None)):
    from loop_engineering.control import start_loop
    result = start_loop(resolve_control_root(resolve_project_root(project=project)))
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
    result = stop_loop(resolve_control_root(resolve_project_root(project=project)))
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.get("/log")
def get_log(project: str = Query(None), lines: int = Query(50)):
    """返回 loop 最近输出（从 Claude session JSONL 读取）."""
    import json, re
    lines = int(lines) if isinstance(lines, (int, str)) else 50
    pr = resolve_control_root(resolve_project_root(project=project)).replace("\\", "/")
    claude_name = re.sub(r'^([a-z]):/', r'\1--', pr.lower())
    claude_name = re.sub(r'[^a-z0-9]', '-', claude_name)
    base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(base):
        return Response(status_code=200, content="(no sessions)", media_type="text/plain")
    session_dir = os.path.join(base, claude_name)
    if not os.path.isdir(session_dir):
        return Response(status_code=200, content="(no sessions yet)", media_type="text/plain")
    # 找 loop cmd 启动的 session 文件（而非任意 Claude 窗口）
    from loop_engineering.control import find_loop_session_file
    session_file = find_loop_session_file(pr, session_dir)
    if not session_file:
        return Response(status_code=200, content="(no sessions yet)", media_type="text/plain")
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        # 取最近的 assistant 文本消息
        output = []
        for line in all_lines[-lines * 5:]:  # 多读一些，因为不是每行都是文本
            try:
                msg = json.loads(line)
                content = msg.get("message", {}).get("content", [])
                role = msg.get("message", {}).get("role", "")
                if role == "assistant":
                    for c in content if isinstance(content, list) else [content]:
                        if isinstance(c, dict) and c.get("type") == "text":
                            output.append(c.get("text", ""))
            except Exception:
                pass
        import markdown as md
        html = md.markdown("\n\n---\n\n".join(output[-lines:]), extensions=['fenced_code', 'tables'])
        # 注入 dashboard 样式
        html = f"<style>pre{{background:var(--surface2);padding:8px 12px;border-radius:6px;overflow-x:auto}}code{{font-size:12px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:4px 8px;border:1px solid var(--border);text-align:left}}h1,h2,h3{{color:var(--text);margin:8px 0}}p{{margin:4px 0}}ul,ol{{padding-left:20px}}blockquote{{border-left:3px solid var(--pass);padding-left:12px;color:var(--muted)}}</style>{html}"
        return Response(status_code=200, content=html, media_type="text/html")
    except Exception as e:
        return Response(status_code=200, content=f"(error: {e})", media_type="text/plain")


@router.post("/focus")
def focus_window(project: str = Query(None)):
    """激活 Loop 终端窗口（通过 PID）."""
    import platform
    if platform.system() != "Windows":
        return Response(status_code=200, content="Not Windows", media_type="text/plain")

    pr = resolve_control_root(resolve_project_root(project=project))
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
