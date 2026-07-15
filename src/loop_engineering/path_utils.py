"""Loop Engineering 路径工具函数.

集中提供项目根目录查找、分支检测、agent 目录计算等工具函数，
替代分散在各模块中的 _find_project_root / _project_root / _default_branch 私有实现。
"""

import os


def find_project_root(start_dir=None):
    """从 start_dir（默认 cwd）向上搜索 loop-engineering 项目根目录。

    查找标记: .loop-engineering/loop-config.yaml 或根目录 loop-config.yaml（兼容旧项目）。
    如果不在任何项目内，返回当前工作目录作为兜底。

    Args:
        start_dir: 搜索起点目录，默认为 os.getcwd()

    Returns:
        项目根目录的绝对路径
    """
    if start_dir is None:
        start_dir = os.getcwd()
    start_dir = os.path.abspath(start_dir)

    from loop_engineering.config import is_project_dir

    p = start_dir
    for _ in range(10):
        if is_project_dir(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return start_dir  # fallback


def resolve_project_root(project=None, request=None):
    """多来源解析项目根目录。

    优先级:
    1. 显式 project 参数
    2. HTTP 请求中的 X-Loop-Project header（如果提供了 request）
    3. 环境变量 LOOP_PROJECT_ROOT
    4. 从 cwd 向上搜索（兜底）

    Args:
        project: 显式指定的项目路径
        request: FastAPI Request 对象（可选），用于读取 X-Loop-Project header

    Returns:
        项目根目录的绝对路径
    """
    # 1. 显式 project 参数
    if project:
        return os.path.abspath(project)

    # 2. HTTP header（前端 HTMX 自动携带）
    if request is not None:
        try:
            header_val = request.headers.get("X-Loop-Project")
            if header_val:
                return os.path.abspath(header_val)
        except Exception:
            pass

    # 3. 环境变量
    env = os.environ.get("LOOP_PROJECT_ROOT")
    if env:
        return os.path.abspath(env)

    # 4. 从 cwd 向上搜索（兜底）
    return find_project_root()


def get_default_branch(repo_path=None):
    """获取默认分支引用，自动检测 master vs main。

    优先级: local master > local main > origin/master > origin/main.

    Args:
        repo_path: git 仓库路径，默认为 os.getcwd()

    Returns:
        分支引用名（如 "master" 或 "main"）
    """
    import subprocess

    def _run(cmd):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                encoding='utf-8', errors='replace', cwd=repo_path, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    for ref in ["master", "main", "origin/master", "origin/main"]:
        if _run(f"git rev-parse --verify {ref}"):
            return ref
    return "master"


def resolve_control_root(project_root):
    """解析控制信号的读写目录。

    task-runner 在 agent worktree 中运行，控制信号（heartbeat/throttle/loop.pid）
    必须写入 agent worktree 的 .loop-engineering/control/，否则 Dashboard 和
    task-runner 操作的是不同的信号文件。

    如果项目配置了 agent worktree 且目录存在，返回 agent worktree 路径；
    否则返回 project_root 本身（兼容未配置 agent worktree 的场景）。

    Args:
        project_root: 主项目根目录绝对路径

    Returns:
        控制信号目录的父目录（通常是 agent worktree 根目录）
    """
    from loop_engineering.config import read_config, get_agent_dir

    cfg = read_config(project_root)
    if cfg and cfg.get("agent", {}).get("workspace"):
        agent_dir = get_agent_dir(cfg)
        if agent_dir and os.path.isdir(agent_dir):
            return agent_dir
    return project_root
