"""Loop Engineering CLI.

用法:
  loop setup --project-root <path> [options]
  loop init
"""

import argparse
import os
import sys

from . import config as cfg
from . import setup


def main():
    parser = argparse.ArgumentParser(
        prog="loop",
        description="Loop Engineering - Agent 自主任务执行系统",
    )
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # loop setup
    setup_parser = subparsers.add_parser("setup", help="快速搭建 Agent worktree 环境")
    setup_parser.add_argument(
        "--project-root", required=True, help="项目根目录路径"
    )
    setup_parser.add_argument(
        "--agent-name", default=None, help="Agent 名称（用于任务分配，默认自动读取 git config user.name）"
    )
    setup_parser.add_argument(
        "--data-repo", default=None, help="配表/数据仓库路径（可选）"
    )
    setup_parser.add_argument(
        "--agent-workspace", default=None, help="Agent 工作区目录（默认自动检测）"
    )
    setup_parser.add_argument(
        "--agent-port", type=int, default=None, help="Agent MCP 端口（默认 9080）"
    )
    setup_parser.add_argument(
        "--main-port", type=int, default=None, help="主工程 MCP 端口（默认 8080）"
    )
    setup_parser.add_argument(
        "--force", action="store_true", help="忽略非致命错误继续执行"
    )
    setup_parser.add_argument(
        "-y", "--yes", action="store_true", help="跳过确认提示，直接执行"
    )
    setup_parser.add_argument(
        "--type", default=None, help="项目类型预设 (unity-tolua, node-frontend, go-backend, generic)"
    )

    # loop init
    subparsers.add_parser("init", help="交互式向导模式")

    # loop ui
    ui_parser = subparsers.add_parser("ui", help="Dashboard 管理")
    ui_sub = ui_parser.add_subparsers(dest="ui_command")
    ui_start = ui_sub.add_parser("start", help="启动 Dashboard")
    ui_start.add_argument("--port", type=int, default=8765, help="端口（默认 8765）")
    ui_start.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")

    # loop config
    config_parser = subparsers.add_parser("config", help="查看或修改项目配置")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_show = config_sub.add_parser("show", help="查看当前配置")
    config_show.add_argument("--project-root", default=None, help="项目根目录")
    config_set = config_sub.add_parser("set", help="修改配置项")
    config_set.add_argument("pairs", nargs="+", metavar="KEY=VALUE",
                            help="配置项，如 agent.name=foo main.mcp_port=8081")
    config_set.add_argument("--project-root", default=None, help="项目根目录")

    # loop teardown
    teardown_parser = subparsers.add_parser("teardown", help="移除 loop-engineering（仅删 agent worktree + 注册表）")
    teardown_parser.add_argument("--project-root", default=None, help="项目根目录")
    teardown_parser.add_argument("--force", "-y", action="store_true", help="跳过确认")
    teardown_parser.add_argument("--dry-run", action="store_true", help="仅显示将要删除的内容")

    args = parser.parse_args()

    if args.command == "setup":
        _cmd_setup(args)
    elif args.command == "init":
        _cmd_init()
    elif args.command == "ui":
        _cmd_ui(args)
    elif args.command == "config":
        _cmd_config(args)
    elif args.command == "teardown":
        _cmd_teardown(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_setup(args):
    """快速 setup 模式."""
    project_root = os.path.abspath(args.project_root)

    if not os.path.isdir(project_root):
        print(f"错误: 项目目录不存在: {project_root}")
        sys.exit(1)

    # 自动检测
    print("正在检测项目配置...")
    detected = cfg.detect_config(project_root)
    print()

    # 构建最终配置：CLI 参数覆盖自动检测
    config = detected.copy()

    if args.agent_name:
        config["agent"]["name"] = args.agent_name

    # agent name 从 git config 自动读取，也可通过 --agent-name 覆盖
    agent_name = config["agent"]["name"]
    if not agent_name:
        print("错误: 未检测到 agent 名称，请先执行 git config user.name <你的名字> 或用 --agent-name 指定")
        sys.exit(1)
    print(f"  Agent 名称: {agent_name}（来自 git config user.name）")

    if args.agent_workspace:
        config["agent"]["workspace"] = os.path.abspath(args.agent_workspace)
    if args.agent_port:
        config["agent"]["mcp_port"] = args.agent_port
    if args.main_port:
        config["main"]["mcp_port"] = args.main_port
    if args.data_repo:
        config["data_repo"] = {"path": os.path.abspath(args.data_repo)}

    # 应用项目类型预设
    if args.type:
        from loop_engineering.presets import apply_preset, get_preset
        if get_preset(args.type):
            config = apply_preset(config, args.type)
            print(f"  项目类型: {args.type}")
        else:
            print(f"  警告: 未知预设 '{args.type}'，已忽略。可用: unity-tolua, node-frontend, go-backend, generic")

    # 如果没有自动检测到 workspace，使用默认规则
    if not config["agent"]["workspace"]:
        parent = os.path.dirname(project_root)
        config["agent"]["workspace"] = os.path.join(parent, config["project"]["name"] + "-agent")

    # 显示摘要
    _print_summary(config)

    # 确认
    if not args.yes:
        print()
        response = input("确认执行? [Y/n]: ").strip().lower()
        if response and response not in ("y", "yes", ""):
            print("已取消")
            sys.exit(0)

    # 执行
    setup.run_setup(config, force=args.force)


def _cmd_init():
    """向导模式."""
    print("=" * 50)
    print("Loop Engineering Setup — 向导模式")
    print("=" * 50)
    print()

    # 1. 项目路径
    while True:
        project_root = input("项目根目录路径: ").strip()
        project_root = os.path.abspath(project_root)
        if os.path.isdir(project_root):
            break
        print(f"  目录不存在: {project_root}")

    print(f"  项目名称: {os.path.basename(project_root)}")
    print()

    # 2. 检测
    print("正在检测项目配置...")
    detected = cfg.detect_config(project_root)
    config = detected.copy()

    # 显示检测结果
    if detected.get("_detected", {}).get("unity"):
        print("  ✓ 检测到 Unity 工程")
    print(f"  主 MCP 端口: {config['main']['mcp_port']}")
    print()

    # 3. Agent 名称
    default_name = config["agent"]["name"] or ""
    name_input = input(f"Agent 名称 [{default_name}]: ").strip()
    config["agent"]["name"] = name_input if name_input else default_name

    if not config["agent"]["name"]:
        print("错误: 必须指定 Agent 名称")
        sys.exit(1)

    # 4. Agent workspace
    default_ws = config["agent"]["workspace"]
    ws_input = input(f"Agent 工作区目录 [{default_ws}]: ").strip()
    if ws_input:
        config["agent"]["workspace"] = os.path.abspath(ws_input)

    # 5. Agent MCP 端口
    default_agent_port = config["agent"]["mcp_port"]
    port_input = input(f"Agent MCP 端口 [{default_agent_port}]: ").strip()
    if port_input:
        config["agent"]["mcp_port"] = int(port_input)

    # 6. Data repo
    data_repo = config.get("data_repo", {}).get("path", "")
    data_input = input(f"配表/数据仓库路径 [{data_repo or '无'}]: ").strip()
    if data_input and data_input.lower() != "无":
        config["data_repo"] = {"path": os.path.abspath(data_input)}
    elif not data_repo:
        if "data_repo" in config:
            del config["data_repo"]

    # 7. Project type
    from loop_engineering.presets import list_presets, apply_preset
    presets = list_presets()
    print("\n可用项目类型预设:")
    for key, name, desc in presets:
        print(f"  {key}: {name} — {desc}")
    type_input = input(f"项目类型 [{config.get('type', 'skip')}]: ").strip()
    if type_input and type_input.lower() != "skip":
        if type_input in dict((k, v) for k, v, _ in presets):
            config = apply_preset(config, type_input)

    print()

    # 显示摘要
    _print_summary(config)

    # 确认
    response = input("确认执行? [Y/n]: ").strip().lower()
    if response and response not in ("y", "yes", ""):
        print("已取消")
        sys.exit(0)

    setup.run_setup(config)


def _find_project_root():
    """从当前目录向上查找 loop-config.yaml，返回项目根目录路径."""
    from loop_engineering.config import is_project_dir
    p = os.getcwd()
    for _ in range(10):
        if is_project_dir(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None


def _cmd_config(args):
    """查看或修改项目配置."""
    pr = args.project_root
    if pr:
        pr = os.path.abspath(pr)
    else:
        pr = _find_project_root()

    if not pr:
        print("错误: 未找到 loop-config.yaml，请指定 --project-root 或在项目目录下运行")
        sys.exit(1)

    if not os.path.exists(os.path.join(pr, ".loop-engineering", "loop-config.yaml")):
        print(f"错误: {pr} 下没有 .loop-engineering/loop-config.yaml，请先执行 setup")
        sys.exit(1)

    if args.config_command == "set":
        # 解析 KEY=VALUE 对
        updates = {}
        for pair in args.pairs:
            if "=" not in pair:
                print(f"错误: 格式应为 KEY=VALUE，收到: {pair}")
                sys.exit(1)
            key, value = pair.split("=", 1)
            key = key.strip()
            value = value.strip()

            # 解析嵌套 key (如 agent.name → agent: {name: ...})
            parts = key.split(".")
            current = updates
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            # 尝试类型转换
            try:
                value = int(value)
            except ValueError:
                pass
            current[parts[-1]] = value

        from loop_engineering.config import merge_config, write_config
        new_config, changed = merge_config(pr, updates)
        write_config(pr, new_config)
        print(f"已更新 {len(changed)} 项: {', '.join(sorted(changed))}")

        # 副作用
        if changed & {"agent.mcp_port", "main.mcp_port"}:
            from loop_engineering.setup import generate_mcp_configs, sync_to_agent
            generate_mcp_configs(new_config)
            sync_to_agent(new_config)
            print("  → MCP 配置已重新生成并同步")
        if changed & {"agent.name", "project.name"}:
            from loop_engineering.setup import render_skill_md
            render_skill_md(new_config)
            print("  → task-runner SKILL.md 已重新渲染")
    else:
        # show (默认)
        from loop_engineering.config import read_config
        cfg = read_config(pr)
        if not cfg:
            print("(空配置)")
        else:
            _print_summary(cfg)
            if cfg.get("type"):
                print(f"  类型:     {cfg['type']}")


def _cmd_teardown(args):
    """移除 loop-engineering（仅删 agent worktree + 注册表）."""
    pr = args.project_root
    if pr:
        pr = os.path.abspath(pr)
    else:
        pr = _find_project_root()

    if not pr:
        print("错误: 未找到 loop-config.yaml，请指定 --project-root 或在项目目录下运行")
        sys.exit(1)

    from loop_engineering.config import read_config
    cfg = read_config(pr)
    if not cfg:
        print("错误: loop-config.yaml 不存在或为空")
        sys.exit(1)

    project_name = cfg.get("project", {}).get("name", os.path.basename(pr))

    if args.dry_run:
        print(f"[Dry-run] 将移除以下内容:")
        agent_ws = cfg.get("agent", {}).get("workspace", "")
        if agent_ws:
            print(f"  - Agent worktree: {os.path.join(agent_ws, project_name)}")
            data_repo = cfg.get("data_repo", {}).get("path")
            if data_repo:
                print(f"  - Data worktree: {os.path.join(agent_ws, os.path.basename(data_repo))}")
        print(f"  - loop-config.yaml: {pr}\\.loop-engineering\\loop-config.yaml")
        print(f"  - 从注册表移除: {project_name}")
        return

    if not args.force:
        print(f"将移除 {project_name} 的 agent worktree 和注册表条目。")
        print(f"主项目文件不受影响。")
        print()
        confirm = input(f"输入项目名 '{project_name}' 以确认: ").strip()
        if confirm != project_name:
            print("已取消")
            sys.exit(0)

    from loop_engineering.setup import run_teardown
    result = run_teardown(pr, force=args.force, dry_run=False)
    if result["removed"]:
        print(f"\n✓ 已移除 {project_name}")
    else:
        print(f"\n✗ 移除失败")
        for w in result.get("warnings", []):
            print(f"  ! {w}")


def _print_summary(config):
    """打印配置摘要."""
    print("--- 配置摘要 ---")
    print(f"  项目:     {config['project']['name']}")
    print(f"  根目录:   {config['project']['root']}")
    print(f"  Agent:    {config['agent']['name']}")
    print(f"  Agent WS: {config['agent']['workspace']}")
    print(f"  MCP 端口: 主 {config['main']['mcp_port']} / Agent {config['agent']['mcp_port']}")
    if config.get("data_repo"):
        print(f"  Data repo: {config['data_repo']['path']}")
    else:
        print(f"  Data repo: (无)")


def _cmd_ui(args):
    """Dashboard 管理."""
    if args.ui_command == "start":
        _find_and_start_ui(args)
    else:
        print("用法: loop ui start [--port 8765]")
        sys.exit(1)


def _find_and_start_ui(args):
    """从当前目录向上查找 loop-config.yaml，启动 Dashboard."""
    from loop_engineering.server.app import start_server
    from loop_engineering.config import is_project_dir

    p = os.getcwd()
    project_root = p
    for _ in range(10):
        if is_project_dir(p):
            project_root = p
            break
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent

    print(f"Project: {project_root}")
    print(f"Dashboard: http://localhost:{args.port}")
    start_server(project_root, port=args.port, open_browser=not args.no_browser)
