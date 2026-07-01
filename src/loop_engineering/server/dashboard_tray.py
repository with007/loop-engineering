"""Loop Engineering Dashboard — 系统托盘应用.

双击 exe 启动：
- 后台运行 uvicorn Dashboard 服务器
- 系统托盘图标 + 右键菜单
- 定时轮询 Loop 状态
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime

# ── 日志 ──
EXE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
LOG_PATH = os.path.join(EXE_DIR, "dashboard.log")


def _log(msg):
    """记录操作日志."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

import pystray
from PIL import Image, ImageDraw

# ── 路径 ──
EXE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
SETTINGS_PATH = os.path.join(EXE_DIR, "dashboard-settings.json")
ICON_SIZE = 64


# ── 设置 ──
def load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"port": 8765, "autostart": True}


def save_settings(settings):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


settings = load_settings()
PORT = int(settings.get("port", 8765))
AUTOSTART = settings.get("autostart", False)


# ── 生成图标 ──
def _create_base_icon():
    """生成基础图标：蓝底圆形 + 'L'."""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 蓝底圆形
    margin = 4
    draw.ellipse(
        [margin, margin, ICON_SIZE - margin, ICON_SIZE - margin],
        fill=(59, 130, 246, 255),  # var(--pass) blue
    )

    # 白色 'L' 字母
    draw.text((ICON_SIZE // 2 - 5, ICON_SIZE // 2 - 14), "L", fill=(255, 255, 255, 255))

    return img


def _add_badge(base_img, count):
    """在图标右下角叠加红点角标."""
    if count <= 0:
        return base_img

    img = base_img.copy()
    draw = ImageDraw.Draw(img)

    # 红点
    radius = 16
    cx, cy = ICON_SIZE - radius - 4, ICON_SIZE - radius - 4
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(249, 115, 22, 255),  # var(--fail) orange
    )

    # 数字
    text = str(count) if count < 10 else "!"
    draw.text((cx - 5, cy - 10), text, fill=(255, 255, 255, 255))

    return img


BASE_ICON = _create_base_icon()


def make_icon(badge_count=0):
    return _add_badge(BASE_ICON, badge_count)


# ── 端口工具 ──
def is_port_available(port):
    """检查端口是否可用."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        return False


def find_available_port(start=8765):
    """从 start 开始找到第一个可用端口."""
    for port in range(start, start + 20):
        if is_port_available(port):
            return port
    return start  # fallback


# ── 全局状态 ──
loop_running = False
loop_paused = False
heartbeat_time = ""
current_task = ""
pending_merge_count = 0
projects = []  # list of {"name": ..., "root": ..., "agent_dir": ...}
agent_name = ""  # 当前 agent 名称
_tray_icon = None  # pystray Icon 实例，用于项目列表变化时重建菜单


# ── uvicorn 服务器 ──
_server_thread = None
_server_stop = threading.Event()


def _run_server(port):
    """在独立线程中运行 uvicorn."""
    os.environ.pop("LOOP_PROJECT_ROOT", None)

    # PyInstaller --windowed 下 sys.stdout/stderr 为 None，uvicorn logging 需要
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    import uvicorn
    from loop_engineering.server.app import app

    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception:
        _log(f"SERVER CRASH:\n{traceback.format_exc()}")
        raise


def start_server(port):
    """启动 uvicorn 后台线程，等待服务器就绪."""
    global _server_thread, _server_stop
    if _server_thread and _server_thread.is_alive():
        return

    _server_stop.clear()
    _server_thread = threading.Thread(target=_run_server, args=(port,), daemon=True)
    _server_thread.start()

    # 等待服务器就绪（最多 10 秒）
    for i in range(20):
        time.sleep(0.5)
        if not _server_thread.is_alive():
            # 线程已死，检查错误日志
            log_path = os.path.join(EXE_DIR, "dashboard-error.log")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    print(f"Server crash:\n{f.read()}", file=sys.stderr)
            break
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return  # 服务器就绪
        except (OSError, ConnectionRefusedError):
            continue


def is_server_alive():
    """检查 uvicorn 是否在监听端口."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("127.0.0.1", PORT))
        s.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def restart_server(port):
    """重启服务器到新端口."""
    global _server_thread
    _server_stop.set()
    if _server_thread and _server_thread.is_alive():
        _server_thread.join(timeout=3)
    start_server(port)


# ── 轮询引擎 ──
_poll_thread = None
_poll_stop = threading.Event()


def _read_control_status(project_root):
    """读取项目的 loop 控制状态."""
    status = {"running": False, "paused": False, "heartbeat": ""}
    control_dir = os.path.join(project_root, ".loop-engineering", "control")
    if not os.path.isdir(control_dir):
        return status

    # heartbeat
    hb_path = os.path.join(control_dir, "heartbeat")
    if os.path.exists(hb_path):
        try:
            with open(hb_path, "r", encoding="utf-8") as f:
                status["heartbeat"] = f.read().strip()
            # 心跳在 5 分钟内视为 running
            try:
                hb_time = datetime.fromisoformat(status["heartbeat"])
                if (datetime.now() - hb_time).total_seconds() < 300:
                    status["running"] = True
            except Exception:
                pass
        except Exception:
            pass

    # pause
    pause_path = os.path.join(control_dir, "pause")
    if os.path.exists(pause_path):
        status["paused"] = True

    # pid
    pid_path = os.path.join(control_dir, "loop.pid")
    if os.path.exists(pid_path) and not status["running"]:
        # pid 文件存在但心跳过期 → 进程可能挂了
        status["running"] = False

    return status


def _read_tasks_status(project_root, whoami):
    """读取 tasks.md 中当前 agent 的任务状态."""
    tasks_path = os.path.join(project_root, "tasks.md")
    if not os.path.exists(tasks_path):
        return {"current_task": "", "pending_merge": 0}

    result = {"current_task": "", "pending_merge": 0}
    try:
        with open(tasks_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                # 检查是否分配给当前 agent
                if f"(→ {whoami})" not in line:
                    continue
                if line.startswith("- [~]"):
                    # 进行中
                    result["current_task"] = line.lstrip("- [~] ").split(" (→")[0].strip()
    except Exception:
        pass

    return result


def _count_unmerged_branches(project_root, whoami):
    """统计待合入的 agent 分支数."""
    try:
        # 列出远程 agent 分支
        result = subprocess.run(
            f'git branch -r --list "origin/agent/{whoami}/*"',
            shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            cwd=project_root, timeout=10,
        )
        branches = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        if not branches:
            return 0

        # 排除已合入的分支
        unmerged = 0
        from loop_engineering.git_utils import is_merged
        for branch in branches:
            if not is_merged(branch, is_remote=True, repo_path=project_root):
                unmerged += 1
        return unmerged
    except Exception:
        return 0


def _load_projects():
    """加载注册的项目列表."""
    try:
        from loop_engineering.registry import list_projects
        from loop_engineering.config import is_project_dir, read_config

        result = []
        for p in list_projects():
            if not is_project_dir(p["root"]):
                continue
            cfg = read_config(p["root"])
            agent_ws = cfg.get("agent", {}).get("workspace", "")
            project_name = cfg.get("project", {}).get("name", os.path.basename(p["root"]))
            agent_name_from_cfg = cfg.get("agent", {}).get("name", "")
            # agent_dir = workspace/ project_name
            agent_dir = os.path.join(agent_ws, project_name) if agent_ws else ""
            result.append({
                "name": project_name,
                "root": p["root"],
                "agent_dir": agent_dir,
                "agent_name": agent_name_from_cfg,
            })
        return result
    except Exception:
        return []


def _poll_loop():
    """轮询线程：每 5 秒更新全局状态."""
    global loop_running, loop_paused, heartbeat_time, current_task, pending_merge_count, projects, agent_name

    _last_project_names = None

    while not _poll_stop.is_set():
        try:
            # 加载项目列表
            new_projects = _load_projects()

            # 项目列表变化时重建菜单
            new_names = tuple(p["name"] for p in new_projects)
            if new_names != _last_project_names:
                _last_project_names = new_names
                projects = new_projects
                # 重建托盘菜单（项目列表变了）
                if _tray_icon:
                    _tray_icon._menu = pystray.Menu(*build_menu_tuple())
                    _tray_icon.update_menu()

            if projects:
                # 取第一个项目作为主项目
                primary = projects[0]
                agent_name = primary.get("agent_name", "")

                # 读取控制状态
                ctrl = _read_control_status(primary["root"])
                loop_running = ctrl["running"]
                loop_paused = ctrl["paused"]
                heartbeat_time = ctrl.get("heartbeat", "")

                # 读取任务状态
                tasks = _read_tasks_status(primary["root"], agent_name)
                current_task = tasks["current_task"]

                # 统计待合入分支
                pending_merge_count = _count_unmerged_branches(primary["root"], agent_name)
        except Exception:
            pass

        _poll_stop.wait(5)


def start_polling():
    """启动轮询线程."""
    global _poll_thread, _poll_stop
    _poll_stop.clear()
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    _poll_thread.start()


# ── 右键菜单 ──
def _status_text():
    """构建状态行文本."""
    if loop_running:
        if loop_paused:
            return "Loop: 已暂停 ⏸"
        return "Loop: 运行中 ●"
    return "Loop: 未启动 ○"


def _sep():
    return pystray.MenuItem("───────────────", None, enabled=False)


def _loop_control_items():
    """根据状态动态生成 Loop 控制菜单项."""
    items = []
    if loop_running and not loop_paused:
        items.append(pystray.MenuItem("暂停 Loop", _on_pause_loop))
        items.append(pystray.MenuItem("停止 Loop", _on_stop_loop))
    elif loop_running and loop_paused:
        items.append(pystray.MenuItem("恢复 Loop", _on_resume_loop))
        items.append(pystray.MenuItem("停止 Loop", _on_stop_loop))
    else:
        items.append(pystray.MenuItem("启动 Loop", _on_start_loop))
    return items


def _mk_open_project_dashboard(root):
    """工厂函数：打开指定项目的 Dashboard."""
    def _fn():
        _open_project_dashboard(root)
    return _fn


def _mk_open_dir(path):
    """工厂函数：打开指定路径."""
    def _fn():
        _open_dir(path)
    return _fn


def _projects_menu_items():
    """生成项目子菜单."""
    if not projects:
        return []

    if len(projects) == 1:
        p = projects[0]
        sub = []
        sub.append(pystray.MenuItem(
            f"打开 Dashboard",
            _mk_open_project_dashboard(p["root"]),
        ))
        sub.append(pystray.MenuItem(
            "打开目录",
            _mk_open_dir(p["root"]),
        ))
        if p.get("agent_dir"):
            sub.append(pystray.MenuItem(
                "打开 Agent 工作区",
                _mk_open_dir(p["agent_dir"]),
            ))
        return [pystray.MenuItem(f"▶ {p['name']}", pystray.Menu(*sub))]

    # 多项目
    items = []
    for p in projects:
        sub = []
        sub.append(pystray.MenuItem(
            "打开 Dashboard",
            _mk_open_project_dashboard(p["root"]),
        ))
        sub.append(pystray.MenuItem(
            "打开目录",
            _mk_open_dir(p["root"]),
        ))
        if p.get("agent_dir"):
            sub.append(pystray.MenuItem(
                "打开 Agent 工作区",
                _mk_open_dir(p["agent_dir"]),
            ))
        items.append(pystray.MenuItem(p["name"], pystray.Menu(*sub)))
    return items


def build_menu_tuple():
    """构建右键菜单 tuple（静态结构 + 动态 visible/text/checked 回调）."""
    items = []

    # 状态行（动态文本）
    items.append(pystray.MenuItem(
        lambda _: _status_text(), None, enabled=False,
    ))
    items.append(_sep())

    # Loop 控制 — 全部存在，用 visible 控制显示
    items.append(pystray.MenuItem("暂停 Loop", _on_pause_loop,
        visible=lambda _: loop_running and not loop_paused))
    items.append(pystray.MenuItem("恢复 Loop", _on_resume_loop,
        visible=lambda _: loop_running and loop_paused))
    items.append(pystray.MenuItem("停止 Loop", _on_stop_loop,
        visible=lambda _: loop_running))
    items.append(pystray.MenuItem("启动 Loop", _on_start_loop,
        visible=lambda _: not loop_running))
    items.append(_sep())

    # 打开 Dashboard (default = bold)
    items.append(pystray.MenuItem("打开 Dashboard", _open_dashboard, default=True))
    items.append(_sep())

    # 新增项目
    items.append(pystray.MenuItem("新增项目", _open_setup))
    items.append(_sep())

    # 项目列表（结构动态，在 build time 决定，项目变化时重建）
    items.extend(_projects_menu_items())
    items.append(_sep())

    # 设置
    items.append(pystray.MenuItem("设置...", _open_settings))
    items.append(_sep())

    # 开机自启 toggle
    items.append(pystray.MenuItem(
        "开机自启", _toggle_autostart,
        checked=lambda _: AUTOSTART,
    ))
    items.append(_sep())

    # 退出
    items.append(pystray.MenuItem("退出", _on_exit))

    return tuple(items)


# ── 菜单动作 ──
def _open_url(url):
    """用系统默认浏览器打开 URL."""
    _log(f"open_url: {url}")
    if sys.platform == "win32":
        subprocess.Popen(
            f'cmd /c start "" "{url}"',
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log(f"open_url: cmd start spawned")
    else:
        webbrowser.open(url)


def _open_dashboard():
    """打开浏览器到 Dashboard."""
    _log(f"open_dashboard: port={PORT}")
    _open_url(f"http://localhost:{PORT}")


def _open_project_dashboard(root):
    """打开浏览器到指定项目的 Dashboard."""
    from urllib.parse import quote
    url = f"http://localhost:{PORT}/?project={quote(root)}"
    _log(f"open_project_dashboard: root={root}, url={url}")
    _open_url(url)


def _open_setup():
    """打开 /setup 页面."""
    _log(f"open_setup: port={PORT}")
    _open_url(f"http://localhost:{PORT}/setup")


def _open_dir(path):
    """在文件管理器中打开目录."""
    _log(f"open_dir: path={path}")
    if os.path.isdir(path):
        os.startfile(path)


def _on_pause_loop():
    _log("action: pause_loop")
    _post_control_api("pause")


def _on_resume_loop():
    _log("action: resume_loop")
    _post_control_api_resume()


def _on_stop_loop():
    _log("action: stop_loop")
    _post_control_api("stop")


def _on_start_loop():
    _log("action: start_loop")
    _post_control_api("start")


def _post_control_api(action):
    """调用 Dashboard 控制 API."""
    import urllib.request
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:{PORT}/api/control/{action}",
                method="POST",
            ),
            timeout=3,
        )
    except Exception:
        pass


def _post_control_api_resume():
    """调用恢复 API（DELETE）."""
    import urllib.request
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://localhost:{PORT}/api/control/pause",
                method="DELETE",
            ),
            timeout=3,
        )
    except Exception:
        pass


def _toggle_autostart(icon=None):
    """切换开机自启状态."""
    global AUTOSTART
    AUTOSTART = not AUTOSTART
    settings["autostart"] = AUTOSTART
    save_settings(settings)
    _log(f"autostart: {'ON' if AUTOSTART else 'OFF'}")
    if AUTOSTART:
        _enable_autostart()
    else:
        _disable_autostart()


def _enable_autostart():
    """写入注册表 Run 键."""
    import winreg
    try:
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "LoopDashboard", 0, winreg.REG_SZ, exe_path)
        winreg.CloseKey(key)
    except Exception:
        pass


def _disable_autostart():
    """删除注册表 Run 键."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, "LoopDashboard")
        winreg.CloseKey(key)
    except Exception:
        pass


def _open_settings():
    """打开设置 — 用记事本编辑 dashboard-settings.json."""
    _log("open_settings")

    # 确保配置文件存在
    if not os.path.exists(SETTINGS_PATH):
        save_settings({"port": PORT, "autostart": AUTOSTART})

    # 用记事本打开
    os.startfile(SETTINGS_PATH)

    # 提示
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        0,
        "修改配置后重启 Loop Dashboard 生效。\n\n"
        "port: 端口号（默认 8765）\n"
        "autostart: true 或 false",
        "Loop Dashboard 设置",
        0x40  # MB_ICONINFORMATION
    )


def _on_exit(icon=None):
    """退出应用."""
    global _server_stop, _poll_stop
    _log("exit requested")

    # 停止轮询
    _poll_stop.set()

    # 停止服务器
    _server_stop.set()

    # 停止托盘
    if icon:
        icon.stop()


# ── Tooltip 构建 ──
def build_tooltip():
    """构建 hover tooltip 文本."""
    lines = ["Loop Engineering"]
    if loop_running:
        if loop_paused:
            lines.append("Loop: 已暂停")
        else:
            lines.append("Loop: 运行中")
    else:
        lines.append("Loop: 未启动")

    if current_task:
        lines.append(f"任务: {current_task[:40]}{'...' if len(current_task) > 40 else ''}")
    if pending_merge_count > 0:
        lines.append(f"待合入: {pending_merge_count}")
    if heartbeat_time:
        try:
            hb_time = datetime.fromisoformat(heartbeat_time)
            sec = int((datetime.now() - hb_time).total_seconds())
            if sec < 60:
                lines.append(f"心跳: {sec}s ago")
            elif sec < 3600:
                lines.append(f"心跳: {sec // 60}m ago")
            else:
                lines.append(f"心跳: {heartbeat_time[:19].replace('T', ' ')}")
        except Exception:
            pass

    return "\n".join(lines)


# ── 图标刷新（角标） ──
_icon_refresh_stop = threading.Event()


def _refresh_icon_loop(icon):
    """定时刷新图标角标、tooltip."""
    while not _icon_refresh_stop.is_set():
        try:
            icon.icon = make_icon(pending_merge_count)
            icon.title = build_tooltip()
        except Exception:
            pass
        _icon_refresh_stop.wait(5)


def start_icon_refresh(icon):
    """启动图标刷新线程."""
    _icon_refresh_stop.clear()
    t = threading.Thread(target=_refresh_icon_loop, args=(icon,), daemon=True)
    t.start()


# ── 主入口 ──
def main():
    """启动 Dashboard 托盘应用."""
    global PORT, AUTOSTART, settings

    # 读取设置
    settings = load_settings()
    PORT = int(settings.get("port", 8765))
    AUTOSTART = settings.get("autostart", False)

    # 命令行 --port 覆盖配置文件
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            try:
                PORT = int(sys.argv[i + 1])
                _log(f"cmdline: port override -> {PORT}")
            except ValueError:
                pass

    # 应用开机自启
    if AUTOSTART:
        _enable_autostart()
    _log(f"startup: port={PORT}, autostart={AUTOSTART}")

    # 查找可用端口
    actual_port = find_available_port(PORT)
    if actual_port != PORT:
        _log(f"port changed: {PORT} -> {actual_port}")
        PORT = actual_port

    # 启动 uvicorn 服务器
    _log(f"starting server on port {PORT}")
    start_server(PORT)
    _log(f"server check: alive={is_server_alive()}")

    # 打开浏览器
    _log(f"opening browser")
    _open_url(f"http://localhost:{PORT}")

    # 启动轮询
    _log("starting polling")
    start_polling()

    # 首次轮询：等 1 秒让项目列表加载完，避免右键菜单空白
    time.sleep(1)

    # 创建托盘图标
    _log("creating tray icon")
    global _tray_icon
    icon = pystray.Icon(
        "Loop Dashboard",
        make_icon(0),
        "Loop Engineering",
        menu=pystray.Menu(*build_menu_tuple()),
    )
    _tray_icon = icon

    # 启动图标刷新
    start_icon_refresh(icon)
    _log("tray running")

    # 运行托盘（阻塞主线程）
    try:
        icon.run()
    except Exception:
        pass

    # 清理
    _poll_stop.set()
    _icon_refresh_stop.set()
    _server_stop.set()


if __name__ == "__main__":
    main()
