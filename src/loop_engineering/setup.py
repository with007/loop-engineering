"""Loop Engineering 环境搭建.

一键创建 Agent worktree、MCP 配置、PackageCache 共享、脚本部署。
"""

import os
import sys
import json
import shutil
import subprocess
import platform
from pathlib import Path

from . import config as cfg


def _run(cmd, cwd=None, check=False):
    """运行 shell 命令."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=120
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def create_worktrees(config):
    """创建 Agent worktree（含可选的 data repo）.

    幂等：如果 worktree 已存在则跳过。
    """
    print("--- 创建 Agent Worktree ---")
    project_root = config["project"]["root"]
    agent_workspace = config["agent"]["workspace"]
    project_name = config["project"]["name"]
    agent_dir = os.path.join(agent_workspace, project_name)

    # 确保 agent workspace 目录存在
    os.makedirs(agent_workspace, exist_ok=True)

    # 主工程 worktree
    _create_single_worktree(project_root, agent_dir, "主工程")

    # Data repo worktree（可选）
    data_repo = config.get("data_repo", {}).get("path")
    if data_repo:
        data_name = os.path.basename(data_repo)
        data_agent_dir = os.path.join(agent_workspace, data_name)
        _create_single_worktree(data_repo, data_agent_dir, "配表/数据")
    else:
        print("  无 data_repo，跳过")


def _default_branch(repo_path):
    """获取默认分支引用。优先级: local master > local main > origin/master > origin/main."""
    # 按优先级依次尝试
    candidates = [
        "master",        # local master
        "main",          # local main
        "origin/master", # remote master
        "origin/main",   # remote main
    ]
    for branch in candidates:
        code, _, _ = _run(f"git rev-parse --verify {branch}", cwd=repo_path)
        if code == 0:
            return branch
    return "master"  # last resort


def _create_single_worktree(source_repo, target_dir, label):
    """创建单个 git worktree。"""
    # git worktree 中 .git 是文件（不是目录）
    if os.path.exists(os.path.join(target_dir, ".git")):
        print(f"  [OK] {label} worktree 已存在: {target_dir}")
        # 同步
        try:
            rc, _, _ = _run("git fetch origin --prune", cwd=target_dir)
            if rc != 0:
                raise RuntimeError("fetch failed")
        except Exception as e:
            print(f"  [OFFLINE] fetch 失败，跳过同步: {str(e)[:120]}")
        return

    print(f"  创建 {label} worktree ...")

    # 尝试在线 fetch
    online = True
    try:
        rc, _, _ = _run("git fetch origin", cwd=source_repo)
        if rc != 0:
            raise RuntimeError("fetch failed")
    except Exception as e:
        print(f"  [OFFLINE] git fetch 失败: {str(e)[:120]}")
        online = False

    default_ref = _default_branch(source_repo)

    if not online:
        # 离线模式：验证本地是否有可用 ref
        code, _, _ = _run(f"git rev-parse --verify {default_ref}", cwd=source_repo)
        if code != 0:
            raise RuntimeError(
                "无法连接远程且本地无可用分支 (master/main)。请检查网络后重试。"
            )
        print(f"  [OFFLINE] 使用本地分支: {default_ref}")

    # remote ref 可以直接用；local branch 需要 --detach（避免 already checked out）
    if default_ref.startswith("origin/"):
        add_cmd = f'git worktree add "{target_dir}" {default_ref}'
    else:
        add_cmd = f'git worktree add --detach "{target_dir}" {default_ref}'

    code, stdout, stderr = _run(add_cmd, cwd=source_repo)
    if code != 0:
        # first attempt failed — clean up and retry
        print(f"  retrying: {stderr.strip()[:120]}")
        # clean git worktree metadata
        _run("git worktree prune", cwd=source_repo)
        # try to remove orphan directory
        if os.path.exists(target_dir) and not os.path.exists(os.path.join(target_dir, ".git")):
            try:
                shutil.rmtree(target_dir, ignore_errors=True)
            except Exception:
                pass  # may be locked by another process
        # also try git's own remove
        _run(f'git worktree remove --force "{target_dir}"', cwd=source_repo)
        _run(add_cmd, cwd=source_repo, check=True)
    print(f"  [OK] {label} worktree 创建完成: {target_dir}")


def generate_mcp_configs(config):
    """生成主工程和 agent 的 MCP 配置文件.

    - 主工程 .mcp.json → main.mcp_port
    - Agent .mcp.json → agent.mcp_port
    - Agent McpProjectConfig.json → agent.mcp_port
    """
    print("--- 生成 MCP 配置 ---")
    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = os.path.join(agent_workspace, project_name)
    main_port = config["main"]["mcp_port"]
    agent_port = config["agent"]["mcp_port"]

    # 主工程 .mcp.json
    main_mcp = {
        "mcpServers": {
            "UnityMCP": {
                "type": "http",
                "url": f"http://127.0.0.1:{main_port}/mcp"
            }
        }
    }
    _write_json_if_changed(os.path.join(project_root, ".mcp.json"), main_mcp, "主工程 .mcp.json")
    _ensure_gitignore(project_root, ".mcp.json")

    # Agent .mcp.json
    agent_mcp = {
        "mcpServers": {
            "UnityMCP": {
                "type": "http",
                "url": f"http://127.0.0.1:{agent_port}/mcp"
            }
        }
    }
    _write_json_if_changed(os.path.join(agent_dir, ".mcp.json"), agent_mcp, "Agent .mcp.json")

    # Agent McpProjectConfig.json (Unity 特定)
    _write_mcp_project_config(agent_dir, project_name, agent_port, "Agent")

    # 主工程 McpProjectConfig.json
    _write_mcp_project_config(project_root, project_name, main_port, "主工程")
    _ensure_gitignore(project_root, "ProjectSettings/McpProjectConfig.json")


def _write_mcp_project_config(worktree_dir, project_name, port, label):
    """写入 McpProjectConfig.json（仅 Unity 工程）."""
    ps_dir = os.path.join(worktree_dir, "ProjectSettings")
    if not os.path.isdir(ps_dir):
        print(f"  (非 Unity 工程，跳过 {label} McpProjectConfig.json)")
        return
    config = {
        "projectName": project_name,
        "httpBaseUrl": f"http://127.0.0.1:{port}",
        "httpRemoteBaseUrl": "",
        "httpTransportScope": "local",
        "unitySocketPort": 6401,
    }
    _write_json_if_changed(
        os.path.join(ps_dir, "McpProjectConfig.json"),
        config,
        f"{label} McpProjectConfig.json",
    )


def _write_json_if_changed(path, data, label):
    """写入 JSON 文件，如果内容相同则跳过."""
    new_content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            old_content = f.read()
        if old_content.strip() == new_content.strip():
            print(f"  [OK] {label} 已是最新，跳过")
            return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [OK] {label} 已生成")


def _ensure_gitignore(project_dir, entry):
    """确保 .gitignore 包含指定条目."""
    gitignore = os.path.join(project_dir, ".gitignore")
    if os.path.exists(gitignore):
        with open(gitignore, "r", encoding="utf-8") as f:
            content = f.read()
        if entry in content.split("\n"):
            return
    with open(gitignore, "a", encoding="utf-8") as f:
        f.write(f"\n{entry}\n")


def share_package_cache(config):
    """通过 mklink /J 共享 PackageCache 和 PackageManager (仅 Windows + Unity).

    幂等：junction 已存在则跳过。
    """
    print("--- PackageCache 共享 ---")
    if platform.system() != "Windows":
        print("  非 Windows，跳过 PackageCache 共享（仅在 Windows 上使用 mklink /J）")
        return

    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = os.path.join(agent_workspace, project_name)

    # 检查主工程是否有 PackageCache
    main_library = os.path.join(project_root, "Library")
    if not os.path.isdir(main_library):
        print("  主工程 Library/ 不存在（非 Unity 工程？），跳过")
        return

    agent_library = os.path.join(agent_dir, "Library")
    os.makedirs(agent_library, exist_ok=True)

    for folder in ["PackageCache", "PackageManager"]:
        main_path = os.path.join(main_library, folder)
        agent_path = os.path.join(agent_library, folder)

        if not os.path.isdir(main_path):
            print(f"  主工程 Library/{folder}/ 不存在，跳过")
            continue

        # 检查是否已是 junction
        if os.path.isdir(agent_path):
            # 用 dir 检查是否是 junction（需要 Windows 反斜杠路径）
            win_path = agent_path.replace("/", "\\")
            code, stdout, _ = _run(f'cmd.exe /c "dir /AL {win_path}"')
            if "<JUNCTION>" in stdout:
                print(f"  [OK] Library/{folder} junction 已存在，跳过")
                continue
            else:
                print(f"  删除现有 Library/{folder} 后创建 junction ...")
                # junction 不能用 shutil.rmtree 删除，用 rmdir
                _run(f'cmd.exe /c "rmdir {win_path}"')
                if os.path.exists(agent_path):
                    print(f"  [FAIL] 无法删除 Library/{folder}")
                    continue

        cmd = f'cmd.exe /c "mklink /J {agent_path} {main_path}"'
        code, stdout, stderr = _run(cmd)
        if code == 0:
            print(f"  [OK] Library/{folder} junction 已创建")
        else:
            print(f"  [FAIL] Library/{folder} junction 创建失败: {stderr}")


def deploy_scripts(config):
    """复制环境脚本到 .claude/scripts/.

    幂等：文件已存在且内容相同时跳过。
    """
    print("--- 部署环境脚本 ---")
    project_root = config["project"]["root"]
    target_dir = os.path.join(project_root, ".claude", "scripts")
    os.makedirs(target_dir, exist_ok=True)

    # 源目录：loop-engineering 包中的 templates/scripts/
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(os.path.dirname(pkg_dir), "templates", "scripts")

    if not os.path.isdir(src_dir):
        print(f"  WARNING:: 模板脚本目录不存在: {src_dir}")
        print(f"  (预期在 loop-engineering/templates/scripts/)")
        return

    deployed = 0
    for fname in os.listdir(src_dir):
        src = os.path.join(src_dir, fname)
        dst = os.path.join(target_dir, fname)
        if not os.path.isfile(src):
            continue
        if os.path.exists(dst):
            with open(src, "rb") as fs:
                src_content = fs.read()
            with open(dst, "rb") as fd:
                dst_content = fd.read()
            if src_content == dst_content:
                print(f"  [OK] {fname} 已是最新，跳过")
                continue
        shutil.copy2(src, dst)
        print(f"  [OK] {fname} 已部署")
        deployed += 1

    if deployed == 0:
        print("  所有脚本已是最新")
    else:
        print(f"  共部署 {deployed} 个脚本")


def render_skill_md(config):
    """从 Jinja2 模板渲染 SKILL.md."""
    print("--- 渲染 SKILL.md ---")
    from jinja2 import Environment, BaseLoader

    # 模板内联（避免额外的模板文件依赖问题）
    template_str = SKILL_MD_TEMPLATE
    env = Environment(loader=BaseLoader())
    template = env.from_string(template_str)

    # 构建模板变量
    project_name = config["project"]["name"]
    project_root = config["project"]["root"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = os.path.join(agent_workspace, project_name)
    agent_port = config["agent"]["mcp_port"]
    agent_name = config["agent"]["name"]

    data_repo = config.get("data_repo", {})
    data_repo_path = data_repo.get("path", "")
    data_repo_name = os.path.basename(data_repo_path) if data_repo_path else ""

    rendered = template.render(
        project_name=project_name,
        project_root=project_root.replace("\\", "/"),
        agent_workspace=agent_workspace.replace("\\", "/"),
        agent_dir=agent_dir.replace("\\", "/"),
        agent_port=agent_port,
        agent_name=agent_name,
        data_repo_path=data_repo_path.replace("\\", "/"),
        data_repo_name=data_repo_name,
        has_data_repo=bool(data_repo_path),
        default_ref=_default_branch(project_root),
        tasks_path=os.path.join(project_root, "tasks.md").replace("\\", "/"),
        is_unity=config.get("type", "").startswith("unity-"),
        project_type=config.get("type", "generic"),
    )

    target_dir = os.path.join(project_root, ".claude", "skills", "task-runner")
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, "SKILL.md")

    # 检查内容是否变化
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            old = f.read()
        if old == rendered:
            print(f"  跳过 SKILL.md（内容相同）")
            return

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(rendered)
    print(f"  [OK] SKILL.md 已生成: {target_path}")


def register_protocol(config):
    """注册 taskrunner:// 协议（仅 Windows）."""
    print("--- 注册通知协议 ---")
    if platform.system() != "Windows":
        print("  非 Windows，跳过协议注册")
        return

    project_root = config["project"]["root"]
    ps1_path = os.path.join(project_root, ".claude", "scripts", "register-protocol.ps1")

    if not os.path.exists(ps1_path):
        print(f"  WARNING:: {ps1_path} 不存在，跳过")
        return

    code, stdout, stderr = _run(f'powershell -ExecutionPolicy Bypass -File "{ps1_path}"')
    if code == 0:
        print(f"  [OK] taskrunner:// 协议已注册")
    else:
        print(f"  [FAIL] 协议注册失败: {stderr}")


def sync_to_agent(config):
    """同步 gitignored 文件到 agent worktree.

    .mcp.json + loop-config.yaml 包含机器特定配置，不提交 git。
    需要手动复制到 agent worktree。
    """
    print("--- 同步配置到 Agent Worktree ---")
    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = os.path.join(agent_workspace, project_name)

    if not os.path.isdir(agent_dir):
        print(f"  [FAIL] Agent worktree 不存在: {agent_dir}")
        return

    # 同步前先 fetch 确保 agent worktree 有最新 refs
    try:
        rc, _, _ = _run("git fetch origin", cwd=agent_dir)
        if rc != 0:
            raise RuntimeError("fetch failed")
    except Exception as e:
        print(f"  [OFFLINE] fetch 失败，仍继续同步文件: {str(e)[:120]}")

    for fname in ["loop-config.yaml", ".mcp.json"]:
        src = os.path.join(project_root, fname)
        dst = os.path.join(agent_dir, fname)
        if not os.path.exists(src):
            print(f"  跳过 {fname}（不存在）")
            continue
        if _file_changed(src, dst):
            shutil.copy2(src, dst)
            print(f"  [OK] {fname} 已同步")
        else:
            print(f"  跳过 {fname}（内容相同）")


def add_unity_mcp(config):
    """添加 Unity MCP 包依赖到 Packages/manifest.json."""
    print("--- Unity MCP 依赖 ---")
    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = os.path.join(agent_workspace, project_name)

    pkg = "com.coplaydev.unity-mcp"
    pkg_url = "https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main"

    for worktree, label in [(project_root, "主工程"), (agent_dir, "Agent")]:
        manifest = os.path.join(worktree, "Packages", "manifest.json")
        if not os.path.exists(manifest):
            print(f"  (非 Unity 工程，跳过 {label})")
            continue

        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)

        deps = data.setdefault("dependencies", {})
        if pkg in deps:
            print(f"  [OK] {label} 已有 unity-mcp")
            continue

        deps[pkg] = pkg_url
        with open(manifest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  [OK] {label} 已添加 unity-mcp")


def deploy_skills(config):
    """部署 Claude Code skills、commands 和 settings."""
    print("--- 部署 Skill 和 Command ---")
    project_root = config["project"]["root"]
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(os.path.dirname(pkg_dir), "templates")

    # Skills
    skills_src = os.path.join(templates_dir, "skills")
    if os.path.isdir(skills_src):
        skills_dst = os.path.join(project_root, ".claude", "skills")
        for name in os.listdir(skills_src):
            src = os.path.join(skills_src, name, "SKILL.md")
            dst = os.path.join(skills_dst, name, "SKILL.md")
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if _file_changed(src, dst):
                    shutil.copy2(src, dst)
                    print(f"  [OK] skill: {name}")
                else:
                    print(f"  跳过 skill: {name}（内容相同）")

    # Commands
    cmds_src = os.path.join(templates_dir, "commands")
    if os.path.isdir(cmds_src):
        cmds_dst = os.path.join(project_root, ".claude", "commands")
        for name in os.listdir(cmds_src):
            src = os.path.join(cmds_src, name)
            dst = os.path.join(cmds_dst, name)
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if _file_changed(src, dst):
                    shutil.copy2(src, dst)
                    print(f"  [OK] command: {name}")
                else:
                    print(f"  跳过 command: {name}（内容相同）")

    # Settings
    settings_src = os.path.join(templates_dir, "config", "settings.local.json")
    if os.path.exists(settings_src):
        settings_dst = os.path.join(project_root, ".claude", "settings.local.json")
        if _file_changed(settings_src, settings_dst):
            shutil.copy2(settings_src, settings_dst)
            print(f"  [OK] settings.local.json")
        else:
            print(f"  跳过 settings.local.json（内容相同）")


def _file_changed(src, dst):
    """检查目标文件是否需要更新."""
    if not os.path.exists(dst):
        return True
    try:
        with open(src, "rb") as fs:
            src_content = fs.read()
        with open(dst, "rb") as fd:
            dst_content = fd.read()
        return src_content != dst_content
    except Exception:
        return True


def run_setup(config, force=False):
    """执行完整 setup 流程.

    按顺序执行所有步骤，每步前显示进度。
    """
    print("=" * 50)
    print(f"Loop Engineering Setup - {config['project']['name']}")
    print("=" * 50)
    print()

    steps = [
        ("创建 Agent Worktree", lambda: create_worktrees(config)),
        ("生成 MCP 配置", lambda: generate_mcp_configs(config)),
        ("PackageCache 共享", lambda: share_package_cache(config)),
        ("部署环境脚本", lambda: deploy_scripts(config)),
        ("部署 Skill 和 Command", lambda: deploy_skills(config)),
        ("添加 Unity MCP 依赖", lambda: add_unity_mcp(config)),
        ("渲染 SKILL.md", lambda: render_skill_md(config)),
        ("注册通知协议", lambda: register_protocol(config)),
        ("同步配置到 Agent Worktree", lambda: sync_to_agent(config)),
    ]

    for i, (label, fn) in enumerate(steps, 1):
        print(f"\n[{i}/{len(steps)}] {label}")
        try:
            fn()
        except Exception as e:
            # avoid UnicodeEncodeError on Windows GBK terminal
            msg = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f"  [FAIL] {msg}")
            if not force:
                raise

    # 写入配置文件
    # 从 config 中移除内部字段（_detected）
    clean_config = {k: v for k, v in config.items() if not k.startswith("_")}
    config_path = cfg.write_config(config["project"]["root"], clean_config)
    _ensure_gitignore(config["project"]["root"], "loop-config.yaml")
    _ensure_gitignore(config["project"]["root"], ".loop-engineering/")

    # 自动提交 setup 产生的文件
    _commit_setup_files(config)

    print()
    print("=" * 50)
    print("[OK] Setup 完成！")
    print()
    print("接下来:")
    agent_dir = os.path.join(config["agent"]["workspace"], config["project"]["name"])
    print(f"  1. 在 Unity Hub 打开 {agent_dir}")
    print(f"  2. 在 Claude Code 中运行 /runloop")
    if not config.get("data_repo"):
        print(f"  (未配置 data_repo，配表/数据相关任务可能无法执行)")


def _commit_setup_files(config):
    """自动将 setup 产生的文件提交到 git."""
    project_root = config["project"]["root"]

    # 检查是否是 git 仓库
    code, _, _ = _run("git rev-parse --git-dir", cwd=project_root)
    if code != 0:
        print("\n  (非 git 仓库，跳过自动提交)")
        return

    # 检查是否有未提交的变更
    code, stdout, _ = _run("git status --porcelain", cwd=project_root)
    if code != 0 or not stdout.strip():
        print("\n  (无需提交)")
        return

    # 添加 setup 产生的文件
    files_to_add = [
        ".claude/",
        "Packages/manifest.json",
        ".gitignore",
    ]
    for f in files_to_add:
        full = os.path.join(project_root, f)
        if os.path.exists(full):
            _run(f'git add "{f}"', cwd=project_root)

    # 提交
    code, stdout, stderr = _run(
        'git commit -m "chore: loop-engineering setup"',
        cwd=project_root
    )
    if code == 0:
        print("\n  [OK] 已自动提交 setup 文件")
    else:
        # 可能 nothing to commit
        if "nothing to commit" in stderr.lower() or "nothing to commit" in stdout.lower():
            print("\n  (无需提交)")
        else:
            print(f"\n  [WARN] 自动提交失败: {stderr.strip()[:120]}")


# ── SKILL.md 模板 ─────────────────────────────────────────────

SKILL_MD_TEMPLATE = """---
name: task-runner
description: >
  通用任务执行器。每轮取一个分配给当前用户的待办，进入 agent worktree 独立分支，
  派发实现/验证子代理，推送后等人合入。实现者不能自己验收，Agent 不能自己合入 master。
user_invocable: true
---

# Task Runner（任务执行器）

你是任务编排 Agent。每轮取一个**分配给你**的待办 → 进入 agent worktree → fork 分支 → 派子代理实现和验证 → 推分支 → 弹通知等人合入。不亲自写代码，不合入 master。

## 关键路径

| 项目 | 路径 |
|------|------|
| 主工作树 | `{{ project_root }}` |
| **Agent 工作树** | `{{ agent_dir }}` |
{% if has_data_repo %}
| Agent 数据工作树 | `{{ agent_workspace }}/{{ data_repo_name }}` |
{% endif %}
| Agent MCP 端口 | HTTP `{{ agent_port }}` |

子代理在 agent worktree 上下文中运行，自动通过 `.mcp.json` 连接 agent Unity MCP（{{ agent_port }}），与主工程（8080）隔离。

## 原则

- **谁的任务谁做** — 只做 `{{ tasks_path }}` 中标记 `(→ 你的名字)` 的任务
- **实现者不能给自己验收** — verifier 是独立子代理
- **Agent 不能自己合入 master** — 推送后等人审查
- **每个任务从 master fork** — 分支 `agent/[用户名]/[任务ID]`，从最新 {{ default_ref }} 创建

## [WARNING] 关键禁令

- **禁止 `git checkout master`** — agent worktree 永远不能 checkout master（master 被主 worktree 占用）。只用 `{{ default_ref }}` 远程引用。
- **同步用 `git fetch origin && git reset --hard {{ default_ref }}`**（detached HEAD），或用 `git checkout -B agent/xxx {{ default_ref }}`（fork 分支）。

## 每轮执行流程

### Step 0: 确认身份 + 判断上下文

Agent 身份从 `loop-config.yaml` 的 `agent.name` 读取：

```bash
# 从 loop-config.yaml 读取 agent name
whoami = $(python -c "import yaml; print(yaml.safe_load(open('loop-config.yaml'))['agent']['name'])")
# 如: "with"
```

**0a. 判断启动位置**：

```bash
if echo "$(pwd)" | grep -q "{{ agent_workspace.replace('\\', '/').rstrip('/').split('/')[-1] }}"; then
  echo "MODE=AGENT"
else
  echo "MODE=MAIN"
fi
```

| 输出 | 模式 | 处理方式 |
|------|------|----------|
| `MODE=AGENT` | **Agent 模式**（最常见） | 已在 agent worktree，直接同步+执行。**禁止 `git checkout master`** |
| `MODE=MAIN` | **主工程模式** | 需要 EnterWorktree 进入 agent worktree |

---

### Agent 模式（已在 agent worktree）

**同步 + 清理**：

```bash
git fetch origin --prune 2>/dev/null || true
# 如果当前在某个 agent 分支上，先 detach
git checkout --detach {{ default_ref }} 2>/dev/null
# 删掉已合入 {{ default_ref }} 的 agent 分支（不是全部删除）
git branch --list "agent/*" --merged {{ default_ref }} | xargs -r git branch -d 2>/dev/null
```

**检查已合入的远程分支**：

```bash
python -m loop_engineering.scripts.task_cleanup $whoami
```

然后直接进入 Step 1 选任务。子代理自动继承当前 worktree 上下文 + agent MCP。

**完成后**：保持当前状态即可，不需要 ExitWorktree。

---

### 主工程模式（在主 worktree 被调用）

**0b. 确保 agent worktree 存在**（首次或手动清理后重建）：

```bash
ls {{ agent_dir }}/.git 2>/dev/null || {
  mkdir -p {{ agent_workspace }}
  cd {{ project_root }}
  git fetch origin
  git worktree prune
  git worktree add {{ agent_dir }} {{ default_ref }}
}
{% if has_data_repo %}
ls {{ agent_workspace }}/{{ data_repo_name }}/.git 2>/dev/null || {
  cd {{ data_repo_path }}
  git fetch origin
  git worktree prune
  git worktree add {{ agent_workspace }}/{{ data_repo_name }} {{ default_ref }}
}
{% endif %}
```

**0c. 进入 agent worktree**：

调用 `EnterWorktree(path="{{ agent_dir }}")`。

此后会话切换到 agent worktree，`.mcp.json` → MCP {{ agent_port }}。子代理自动继承。

**0d. 同步 agent worktree**：

```bash
git fetch origin --prune
git checkout --detach {{ default_ref }} 2>/dev/null
git branch --list "agent/*" | xargs -r git branch -D 2>/dev/null
```

**0e. 检查已合入的远程分支**：

```bash
python -m loop_engineering.scripts.task_cleanup $whoami
```

> **注意**：Step 6 完成后必须 `ExitWorktree(action="keep")` 回到主 worktree。

### Step 1: 选任务

**写心跳**（Dashboard 用此判断 loop 是否存活）：

```bash
python -c "from loop_engineering.control import write_heartbeat; write_heartbeat('.')"
```

**检查控制信号**：

```bash
# 暂停检查
python -c "from loop_engineering.control import is_paused; exit(0 if is_paused('.') else 1)" && echo "PAUSED" && exit 0
# throttle 读取
throttle=$(python -c "from loop_engineering.control import get_throttle; print(get_throttle('.'))")
```

**选任务**：

```bash
python -m loop_engineering.scripts.task_pick $whoami --project-root {{ project_root }}
```
- 输出格式: `taskID=xxx desc=... openSpec=true|false`
- `openSpec=true` → 任务关联 `openspec/changes/<taskID>/`，implementer 按 OpenSpec apply 流程处理
- 无匹配则 `NONE` → `ExitWorktree(action="keep")` → 停止。


### Step 2: Fork 分支 + 标记进行中

```bash
# 从最新 {{ default_ref }} 创建分支（覆盖已存在的同名分支）
git checkout -B agent/$whoami/[任务ID] {{ default_ref }}

# 主工程 tasks.md 标记进行中（不提交，只给人看）
# [ ] M6 (→ withg)  改为  [~] M6 (→ withg)
```

### Step 3: 派发实现子代理

用 `Agent` 工具。子代理**不会自动继承** worktree CWD — 必须在 prompt 中显式 cd 到 `{{ agent_dir }}`。

**openSpec=true** 时：

```
## 任务（OpenSpec）
taskID: <taskID>
OpenSpec 路径: openspec/changes/<taskID>/

## 工作目录
你必须在 agent worktree 工作：**{{ agent_dir }}**（不是主工程目录）。

```bash
cd {{ agent_dir }}
git checkout agent/<whoami>/<taskID>
pwd  # 必须输出 {{ agent_dir }}
```

## 你的工作
1. 读 openspec/changes/<taskID>/proposal.md 理解目标与范围
2. 读 openspec/changes/<taskID>/design.md 理解架构决策
3. 读 openspec/changes/<taskID>/tasks.md 获取子任务列表
4. 读 openspec/changes/<taskID>/specs/ 下各 spec 获取详细规格
5. 按 openspec-apply-change 流程逐子任务实现
6. 每个子任务完成后标记 openspec/changes/<taskID>/tasks.md 中的 [ ] → [x]
7. 全部完成后输出变更概要

## 分支
agent/<whoami>/<taskID>

## 规范
遵循 CLAUDE.md，只改必要文件。{% if is_unity %}修改后 refresh_unity + read_console 确认 0 errors。{% else %}修改后确认无语法错误。{% endif %}

## 自主运行
你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**：不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。遇到任何不确定，自己决策、自己执行、输出结果。你是一个纯函数——输入任务，输出结果。如果失败，输出 FAIL + 原因；如果成功，输出 PASS + 变更概要。绝不输出问句。

## 输出
完成后输出"变更概要"：改了哪些文件、每个文件改了什么、影响哪些运行时行为。
```

**openSpec=false** 时：

```
## 任务
<描述 + 验收条件，来自 tasks.md>

## 工作目录
你必须在 agent worktree 工作：**{{ agent_dir }}**（不是主工程目录）。

```bash
cd {{ agent_dir }}
git checkout agent/<whoami>/<taskID>
pwd  # 必须输出 {{ agent_dir }}
```

## 分支
agent/<whoami>/<taskID>

## 规范
遵循 CLAUDE.md，只改必要文件。{% if is_unity %}修改后 refresh_unity + read_console 确认 0 errors。{% else %}修改后确认无语法错误。{% endif %}

## 自主运行
你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**：不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。遇到任何不确定，自己决策、自己执行、输出结果。你是一个纯函数——输入任务，输出结果。如果失败，输出 FAIL + 原因；如果成功，输出 PASS + 变更概要。绝不输出问句。

## 输出
完成代码后，输出一段"变更概要"：改了哪些文件、每个文件改了什么、影响哪些运行时行为。
```

### Step 4: 派发验证子代理

用 `Agent` 工具，独立上下文，只能验证不能改代码。必须显式 cd 到 agent worktree。

**openSpec=true** 时：

```
## 任务（OpenSpec）
taskID: <taskID>
OpenSpec 路径: openspec/changes/<taskID>/

## 工作目录
你必须在 agent worktree 工作：**{{ agent_dir }}**（不是主工程目录）。

```bash
cd {{ agent_dir }}
git log --oneline agent/<whoami>/<taskID> -5  # 确认分支存在
pwd  # 必须输出 {{ agent_dir }}
```

## 变更
分支: agent/<whoami>/<taskID>
<implementer 输出的变更概要>

## 你的工作（只能验证，不能改代码）
1. 读 openspec/changes/<taskID>/proposal.md 确认目标
2. 读 openspec/changes/<taskID>/tasks.md 确认全部子任务 [x]
{% if is_unity %}
3. refresh_unity + read_console → 0 errors
4. 读完整 diff，分析每个变更对应的运行时行为
5. 为每个行为设计 Lua 测试代码
6. 用 register_lua_test 注册，调用 runtime-test skill 执行
7. 输出：PASS 或 FAIL + 原因
{% else %}
3. 读完整 diff，确认变更范围正确、无多余文件
4. 模板变更则渲染检查关键字段；代码变更则确认逻辑正确
5. 输出：PASS 或 FAIL + 原因
{% endif %}
4. 读完整 diff，分析每个变更对应的运行时行为
5. 为每个行为设计 Lua 测试代码，遵循 [AUTO TEST: 名] PASS/FAIL 标记约定
6. 用 register_lua_test 注册，接入 config.json + 入口 requireLua，调用 runtime-test skill 执行
7. 输出：PASS 或 FAIL + 原因（每个测试点单独标注）

## 自主运行
你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**：不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。遇到任何不确定，自己决策、自己执行。你是一个纯函数——输入任务，输出验证结果（PASS/FAIL + 原因）。绝不输出问句。

## retry 上下文（第 2、3 次验证时有）
上次 FAIL:
  - 测试点 A: <原因>
  - 测试点 B: <原因>
implementer 修复说明: <...>
请重点验证上述失败测试点，已通过的可以跳过。
```

**openSpec=false** 时：

```
## 任务
<描述 + 验收条件，来自 tasks.md>

## 工作目录
你必须在 agent worktree 工作：**{{ agent_dir }}**（不是主工程目录）。

```bash
cd {{ agent_dir }}
git log --oneline agent/<whoami>/<taskID> -5  # 确认分支存在
pwd  # 必须输出 {{ agent_dir }}
```

## 变更
分支: agent/<whoami>/<taskID>

## 你的工作（只能验证，不能改代码）
{% if is_unity %}
1. refresh_unity + read_console → 0 errors
2. 读完整 diff，分析每个变更对应的运行时行为
3. 为每个行为设计 Lua 测试代码
4. 用 register_lua_test 注册，调用 runtime-test skill 执行
5. 输出：PASS 或 FAIL + 原因
{% else %}
1. 读完整 diff，确认变更范围正确、无多余文件
2. 模板变更则渲染检查关键字段；代码变更则确认逻辑正确
3. 输出：PASS 或 FAIL + 原因
{% endif %}
2. 读完整 diff，分析每个变更对应的运行时行为
3. 为每个行为设计 Lua 测试代码，遵循 [AUTO TEST: 名] PASS/FAIL 标记约定
4. 用 register_lua_test 注册，接入 config.json + 入口 requireLua，调用 runtime-test skill 执行
5. 输出：PASS 或 FAIL + 原因（每个测试点单独标注）

## 自主运行
你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**：不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。遇到任何不确定，自己决策、自己执行。你是一个纯函数——输入任务，输出验证结果（PASS/FAIL + 原因）。绝不输出问句。

## retry 上下文（第 2、3 次验证时有）
上次 FAIL:
  - 测试点 A: <原因>
  - 测试点 B: <原因>
implementer 修复说明: <...>
请重点验证上述失败测试点，已通过的可以跳过。
```

### Step 5: 结果处理

**PASS**:
1. 检查 `git status`，确认改动文件合理
2. 运行收尾脚本（更新主工程 tasks.md: [~]→[x]、生成 diff、弹通知）：
   ```bash
   python -m loop_engineering.scripts.task_done $whoami [任务ID] [IMP序号] [VFY轮数] --project-root {{ project_root }}
   ```
3. 提交并推送：
   ```bash
   git add <改动的源文件>
   git commit -m "[任务ID] 完成"
   git push origin agent/$whoami/[任务ID] 2>/dev/null || echo "无 remote，跳过推送，保留分支待合入"
   ```
4. 清理本地分支（仅推送成功后才删）：
   ```bash
   if git remote -v | grep -q origin; then
     git checkout --detach {{ default_ref }}
     git branch -D agent/$whoami/[任务ID]
   else
     echo "无 remote，保留分支 agent/$whoami/[任务ID] 待手动合入 {{ default_ref }}"
   fi
   ```

**FAIL**:
```
记录 FAIL 数 → SendMessage 当前 implementer（≤5次，每次携带 FAIL 测试点）
    ├─ FAIL 数收敛（↓）→ 继续
    └─ 5 次不收敛 → 新起 implementer（新鲜上下文，携带全部 FAIL 历史）
                        ├─ 最多 3 个 implementer
                        │   ├─ 收敛 → 继续
                        │   └─ 不收敛 → 下一个
                        └─ 3 个都不收敛 → 交给人
```

**交人时**:
- tasks.md 行尾记录 `IMPx(未收敛)`
- 弹通知：
  ```bash
  python .claude/scripts/notify.py "[任务ID] 需人工介入" "FAIL 数不收敛 IMP1-3"
  ```
- 清理本地分支 → `git checkout --detach {{ default_ref }} && git branch -D agent/$whoami/[任务ID]`

### Step 6: 收尾

| 模式 | 收尾操作 |
|------|----------|
| **Agent 模式** | 无需操作。agent worktree 保持在 detached HEAD，下次复用 |
| **主工程模式** | `ExitWorktree(action="keep")` 回到主 worktree |

等待人审查合入。合入后下轮 Step 0 的 `task_cleanup.py` 自动删远程分支。

## Agent Worktree 维护

### 初始创建（一次性）

由 Step 0a 自动处理。

### PackageCache 共享（节省 1.1GB）

```bash
# 首次创建 worktree 后执行一次
mkdir -p {{ agent_dir }}/Library
cmd.exe /c "mklink /J {{ agent_dir }}\\Library\\PackageCache {{ project_root }}\\Library\\PackageCache"
```

### 手动清理

```bash
cd {{ project_root }}
git worktree remove --force {{ agent_dir }}
git worktree prune
```

## 验收门控

| 门控 | C# | Lua |
|------|-----|-----|
| 编译 | `read_console` 0 errors | N/A |
| 运行时 | 变更驱动的行为验证 | 变更驱动的行为验证 |
| 合入 | **人审查 + 人 merge** | **人审查 + 人 merge** |

## 交给人

FAIL 数不收敛（3 个 implementer 都不收敛）/ 架构变更 / 需改配表 / 任务不清 / >5 文件跨模块

## 输出

```markdown
## [任务ID] 等待合入
**分支**: agent/$whoami/[任务ID] | **编译**: pass | **运行时**: pass
**审查**: git fetch && git diff {{ default_ref }}...origin/agent/$whoami/[任务ID]
```
"""


# ── Teardown ──

def run_teardown(project_root, force=False, dry_run=False):
    """移除 loop-engineering 的 agent worktree 和注册表条目。

    不删除主项目中的文件（.claude/、.mcp.json 等保留）。
    返回 {"removed": bool, "steps": [...], "warnings": [...]}
    """
    from . import config as cfg
    from . import registry

    steps = []
    warnings = []

    def _log(action, ok, detail=""):
        entry = {"action": action, "ok": ok, "detail": detail}
        steps.append(entry)
        if ok:
            print(f"  [OK] {action} {detail}".strip())
        else:
            print(f"  [WARN] {action}: {detail}")

    config = cfg.read_config(project_root)
    if not config:
        _log("读取配置", False, "loop-config.yaml 不存在")
        return {"removed": False, "steps": steps, "warnings": ["config not found"]}

    agent_workspace = config.get("agent", {}).get("workspace", "")
    project_name = config.get("project", {}).get("name", os.path.basename(project_root))

    # 1. 移除主工程 agent worktree
    if agent_workspace:
        agent_dir = os.path.join(agent_workspace, project_name)
        _remove_worktree(project_root, agent_dir, "主工程 agent worktree", force, dry_run, _log)

        # 2. 移除 data repo worktree（如果有）
        data_repo = config.get("data_repo", {}).get("path")
        if data_repo:
            data_name = os.path.basename(data_repo)
            data_agent_dir = os.path.join(agent_workspace, data_name)
            _remove_worktree(data_repo, data_agent_dir, "配表 data worktree", force, dry_run, _log)
    else:
        _log("agent workspace", False, "配置中没有 agent.workspace")

    # 3. 删除 loop-config.yaml
    if not dry_run:
        config_path = os.path.join(project_root, "loop-config.yaml")
        if os.path.exists(config_path):
            os.remove(config_path)
            _log("删除 loop-config.yaml", True)
        else:
            _log("删除 loop-config.yaml", True, "已不存在")
    else:
        _log("删除 loop-config.yaml", True, "(dry-run)")

    # 4. 从注册表移除
    if not dry_run:
        registry.remove_project(project_root)
        _log("从注册表移除", True, project_name)
    else:
        _log("从注册表移除", True, f"(dry-run) {project_name}")

    return {
        "removed": True,
        "steps": steps,
        "warnings": warnings,
    }


def _remove_worktree(source_repo, target_dir, label, force, dry_run, _log):
    """移除单个 git worktree。幂等。"""
    if not os.path.exists(target_dir):
        _log(f"移除 {label}", True, "目录已不存在")
        return

    git_file = os.path.join(target_dir, ".git")
    if not os.path.exists(git_file):
        _log(f"移除 {label}", True, "不是 worktree（无 .git），跳过")
        return

    if dry_run:
        _log(f"移除 {label}", True, f"(dry-run) 将删除 {target_dir}")
        return

    code, stdout, stderr = _run(
        f'git worktree remove --force "{target_dir}"', cwd=source_repo
    )
    if code != 0:
        # fallback: 强制删目录 + prune
        if force and os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
            _run("git worktree prune", cwd=source_repo)
            _log(f"移除 {label}", True, "强制删除目录 + prune")
            return
        _log(f"移除 {label}", False, stderr[:120])
    else:
        _run("git worktree prune", cwd=source_repo)
        _log(f"移除 {label}", True, f"已删除 {target_dir}")
