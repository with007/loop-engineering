"""Loop Engineering 控制信号。

通过文件标记实现 Dashboard 与 Task Runner 之间的 IPC。
所有信号文件位于 .loop-engineering/control/
"""

import os
import time
import subprocess
import platform
from datetime import datetime, timezone, timedelta


def _control_dir(project_root):
    return os.path.join(project_root, ".loop-engineering", "control")


def _ensure_dir(project_root):
    os.makedirs(_control_dir(project_root), exist_ok=True)


def _flag_path(project_root, name):
    return os.path.join(_control_dir(project_root), name)


# ── heartbeat ──

def write_heartbeat(project_root):
    """写入心跳时间戳."""
    _ensure_dir(project_root)
    with open(_flag_path(project_root, "heartbeat"), "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def read_heartbeat(project_root):
    """读取最后心跳时间，返回 datetime 或 None."""
    path = _flag_path(project_root, "heartbeat")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return datetime.fromisoformat(f.read().strip())
    except Exception:
        return None


def is_loop_running(project_root, threshold_minutes=None):
    """判断 loop 是否在运行。

    如果未指定 threshold_minutes，自动取 throttle 的 2 倍（至少 3 分钟）。
    """
    hb = read_heartbeat(project_root)
    if hb is None:
        return False
    if threshold_minutes is None:
        throttle = get_throttle(project_root, "2m")
        threshold_minutes = _parse_duration_minutes(throttle) * 2
        threshold_minutes = max(threshold_minutes, 3)
    return datetime.now(timezone.utc) - hb < timedelta(minutes=threshold_minutes)


def _parse_duration_minutes(s):
    """解析 "2m", "30s", "1h" 为分钟数."""
    s = s.strip().lower()
    if s.endswith("s"):
        return max(int(s[:-1]) / 60, 0.5)
    if s.endswith("h"):
        return int(s[:-1]) * 60
    if s.endswith("m"):
        return int(s[:-1])
    return 2  # default


# ── pause ──

def is_paused(project_root):
    """检查是否暂停."""
    return os.path.exists(_flag_path(project_root, "pause"))


def set_pause(project_root, paused=True):
    """设置或取消暂停."""
    _ensure_dir(project_root)
    path = _flag_path(project_root, "pause")
    if paused:
        open(path, "w").close()
    elif os.path.exists(path):
        os.remove(path)


# ── throttle ──

def get_throttle(project_root, default="2m"):
    """读取 throttle 间隔，默认 2m."""
    path = _flag_path(project_root, "throttle")
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip() or default
    except Exception:
        return default


def set_throttle(project_root, interval):
    """设置 throttle 间隔."""
    _ensure_dir(project_root)
    with open(_flag_path(project_root, "throttle"), "w", encoding="utf-8") as f:
        f.write(interval)


# ── status ──

def get_status(project_root):
    """返回当前控制状态."""
    hb = read_heartbeat(project_root)
    running = is_loop_running(project_root)
    pid = _read_pid(project_root)
    return {
        "paused": running and pid is not None and _pid_alive(pid) and is_paused(project_root),
        "throttle": get_throttle(project_root),
        "running": running and (pid is None or _pid_alive(pid)),
        "heartbeat": hb.isoformat() if hb else None,
        "pid": pid,
    }


# ── loop process management ──

def start_loop(project_root):
    """启动 loop 终端窗口."""
    pid = _read_pid(project_root)
    # PID 存活 = 真的在运行，不允许重复启动
    if is_loop_running(project_root) and pid is not None and _pid_alive(pid):
        return {"started": False, "reason": "already running"}
    # 心跳有效但无 PID = 正在启动中，等 PS1 写入 PID
    if is_loop_running(project_root) and pid is None:
        return {"started": False, "reason": "already starting"}
    # 心跳有效但 PID 已死 = 残留状态，清理后继续
    if is_loop_running(project_root):
        _clear_pid(project_root)
        hb_path = _flag_path(project_root, "heartbeat")
        if os.path.exists(hb_path):
            os.remove(hb_path)

    _ensure_dir(project_root)
    project_name = os.path.basename(project_root)
    set_pause(project_root, False)
    write_heartbeat(project_root)

    if platform.system() == "Windows":
        pid_path = os.path.join(_control_dir(project_root), "loop.pid")
        hb_path = _flag_path(project_root, "heartbeat")
        log_path = os.path.join(_control_dir(project_root), "loop.log")
        run_bat = (
            f"@echo off\r\n"
            f"title Loop: {project_name}\r\n"
            f"cd /d {project_root}\r\n"
            f"claude --dangerously-skip-permissions 2>\"{log_path}\"\r\n"
        )
        bat_path = os.path.join(_control_dir(project_root), "run.bat")
        os.makedirs(os.path.dirname(bat_path), exist_ok=True)
        with open(bat_path, "w") as f:
            f.write(run_bat)
        ps_script = (
            f'$p = Start-Process cmd -ArgumentList \'/k \"{bat_path}\"\' '
            f'-WindowStyle Normal -PassThru;'
            f'[System.IO.File]::WriteAllText(\'{pid_path}\', $p.Id.ToString());'
            # 立即写心跳（不等 while 循环的 30s 间隔）
            f'[System.IO.File]::WriteAllText(\'{hb_path}\', [DateTime]::UtcNow.ToString("o"));'
            # SendKeys
            f'Start-Sleep -Seconds 2;'
            f'$ws = New-Object -ComObject WScript.Shell;'
            f'$ws.AppActivate(\'Loop: {project_name}\');Start-Sleep -Seconds 1;'
            f'$ws.SendKeys(\'/runloop\');Start-Sleep -Milliseconds 300;'
            f'$ws.SendKeys(\'{"{ENTER}"}\');Start-Sleep -Milliseconds 300;'
            f'$ws.SendKeys(\'{"{ENTER}"}\');'
            # 后台持续写心跳，每 30 秒一次，直到窗口关闭
            f'try{{'
            f'while(-not $p.HasExited){{'
            f'[System.IO.File]::WriteAllText(\'{hb_path}\', [DateTime]::UtcNow.ToString("o"));'
            f'Start-Sleep -Seconds 30'
            f'}}'
            f'}}catch{{}};'
            f'Remove-Item \'{hb_path}\' -ErrorAction SilentlyContinue'
        )
        ps_path = os.path.join(_control_dir(project_root), "loop.ps1")
        os.makedirs(os.path.dirname(ps_path), exist_ok=True)
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_script)
        cmd = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{ps_path}"'
    else:
        cmd = (
            f'osascript -e \'tell app "Terminal" to do script '
            f'"cd {project_root} && claude --dangerously-skip-permissions"\''
        )

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Windows: PID 由 ps1 脚本异步写入 loop.pid；非 Windows: 直接用 proc.pid
    if platform.system() != "Windows":
        _write_pid(project_root, proc.pid)

    return {"started": True, "pid": proc.pid}


def stop_loop(project_root):
    """停止 loop 终端窗口."""
    pid = _read_pid(project_root)
    killed = False

    if pid and _pid_alive(pid):
        try:
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True,
                               capture_output=True, timeout=10)
                # 确认进程是否真的被杀掉了
                import time
                time.sleep(1)
                if not _pid_alive(pid):
                    killed = True
            else:
                os.kill(pid, 9)
                killed = True
        except Exception:
            pass

    # 只在确认杀死后才清理 PID 文件
    if killed:
        _clear_pid(project_root)
    # 心跳总是清理（停止后不应继续）
    hb_path = _flag_path(project_root, "heartbeat")
    if os.path.exists(hb_path):
        os.remove(hb_path)
    set_pause(project_root, False)

    return {"stopped": killed, "pid": pid}


def _pid_path(project_root):
    return _flag_path(project_root, "loop.pid")


def _write_pid(project_root, pid):
    with open(_pid_path(project_root), "w") as f:
        f.write(str(pid))


def _read_pid(project_root):
    path = _pid_path(project_root)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _clear_pid(project_root):
    path = _pid_path(project_root)
    if os.path.exists(path):
        os.remove(path)


def _pid_alive(pid):
    """检查进程是否存活."""
    try:
        if platform.system() == "Windows":
            r = subprocess.run(f"tasklist /FI \"PID eq {pid}\" /NH",
                               shell=True, capture_output=True, text=True, timeout=5)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False
