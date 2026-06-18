"""Loop Engineering 控制信号。

通过文件标记实现 Dashboard 与 Task Runner 之间的 IPC。
所有信号文件位于 .loop-engineering/control/
"""

import os


def _control_dir(project_root):
    return os.path.join(project_root, ".loop-engineering", "control")


def _ensure_dir(project_root):
    os.makedirs(_control_dir(project_root), exist_ok=True)


def _flag_path(project_root, name):
    return os.path.join(_control_dir(project_root), name)


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
    return {
        "paused": is_paused(project_root),
        "throttle": get_throttle(project_root),
    }
