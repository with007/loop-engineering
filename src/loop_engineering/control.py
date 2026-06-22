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


# ── next ──

def has_next(project_root):
    """检查是否强制触发下一轮."""
    return os.path.exists(_flag_path(project_root, "next"))


def consume_next(project_root):
    """检查并消费 next 信号（原子操作：检查 + 删除）."""
    path = _flag_path(project_root, "next")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


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
        "paused": is_paused(project_root),
        "throttle": get_throttle(project_root),
        "running": running and pid is not None and _pid_alive(pid),
        "heartbeat": hb.isoformat() if hb else None,
        "pid": pid,
    }


# ── loop process management ──

def start_loop(project_root):
    """启动 loop 终端窗口."""
    if is_loop_running(project_root) and _pid_alive(_read_pid(project_root)):
        return {"started": False, "reason": "already running"}

    _ensure_dir(project_root)
    project_name = os.path.basename(project_root)

    if platform.system() == "Windows":
        loop_bat = (
            f"cd /d {project_root}\r\n"
            f"claude --dangerously-skip-permissions"
        )
        bat_path = os.path.join(_control_dir(project_root), "loop.bat")
        os.makedirs(os.path.dirname(bat_path), exist_ok=True)
        with open(bat_path, "w") as f:
            f.write(loop_bat)
        cmd = f'start "Loop: {project_name}" cmd /k "{bat_path}"'
    else:
        cmd = (
            f'osascript -e \'tell app "Terminal" to do script '
            f'"cd {project_root} && claude --dangerously-skip-permissions"\''
        )

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 记下终端进程 PID（不是 claude 的 PID，但可以用来杀终端窗口）
    _write_pid(project_root, proc.pid)

    return {"started": True, "pid": proc.pid}


def stop_loop(project_root):
    """停止 loop 终端窗口."""
    pid = _read_pid(project_root)
    if not pid:
        return {"stopped": False, "reason": "no pid recorded"}

    killed = False
    if _pid_alive(pid):
        try:
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                               capture_output=True, timeout=10)
            else:
                os.kill(pid, 9)
            killed = True
        except Exception:
            pass

    # 清理 pid 文件
    _clear_pid(project_root)
    # 也清理 pause（stop 后恢复 unpaused 状态）
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
