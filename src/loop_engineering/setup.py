"""Loop Engineering 环境搭建.

一键创建 Agent worktree、MCP 配置、PackageCache 共享、脚本部署。
"""

import os
import sys
import json
import shutil
import subprocess


def _get_templates_root():
    """获取 templates/ 根目录，兼容 PyInstaller 打包和开发模式."""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，templates 在 MEIPASS 下
        return os.path.join(sys._MEIPASS, 'templates')
    else:
        # 开发模式：从 loop_engineering/server/ 向上两级到项目根，再进 templates
        pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(os.path.dirname(pkg_dir), 'templates')
import platform
from pathlib import Path

from . import config as cfg
from .path_utils import get_default_branch
from .config import get_agent_dir, get_data_agent_dir


def _run(cmd, cwd=None, check=False):
    """运行 shell 命令."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        encoding='utf-8', errors='replace', cwd=cwd, timeout=120
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
    agent_dir = get_agent_dir(config)

    # 确保 agent workspace 目录存在
    os.makedirs(agent_workspace, exist_ok=True)

    # 主工程 worktree
    _create_single_worktree(project_root, agent_dir, "主工程")

    # Data repo worktree（可选）
    data_agent_dir = get_data_agent_dir(config)
    if data_agent_dir:
        data_repo = config.get("data_repo", {}).get("path")
        if data_repo:
            _create_single_worktree(data_repo, data_agent_dir, "配表/数据")
        else:
            print("  无 data_repo，跳过")
    else:
        print("  无 data_repo，跳过")


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

    default_ref = get_default_branch(source_repo)

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
    agent_dir = get_agent_dir(config)
    main_port = config["main"]["mcp_port"]
    agent_port = config["agent"]["mcp_port"]

    # 检查是否为 Unity 工程（根据 loop-config.yaml 中的 type 字段）
    is_unity = "unity" in config.get("type", "").lower()

    # 主工程 .mcp.json
    main_servers = {}
    if is_unity:
        main_servers["UnityMCP"] = {"type": "http", "url": f"http://127.0.0.1:{main_port}/mcp"}
    main_mcp = _merge_mcp_config(os.path.join(project_root, ".mcp.json"), main_servers, "主工程 .mcp.json")
    _write_json_if_changed(os.path.join(project_root, ".mcp.json"), main_mcp, "主工程 .mcp.json")
    _ensure_gitignore(project_root, ".mcp.json")

    # Agent .mcp.json — 从主工程配置派生，只改端口，保留所有用户添加的服务器
    import copy
    agent_mcp = copy.deepcopy(main_mcp)
    if is_unity:
        agent_mcp["mcpServers"]["UnityMCP"]["url"] = f"http://127.0.0.1:{agent_port}/mcp"
    _write_json_if_changed(os.path.join(agent_dir, ".mcp.json"), agent_mcp, "Agent .mcp.json")

    if is_unity:
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
    """写入 JSON 文件，如果内容相同则跳过（原子写入）."""
    from loop_engineering.utils import atomic_write

    new_content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            old_content = f.read()
        if old_content.strip() == new_content.strip():
            print(f"  [OK] {label} 已是最新，跳过")
            return
    atomic_write(path, new_content)
    print(f"  [OK] {label} 已生成")


def _merge_mcp_config(path, managed_servers, label):
    """读取现有 .mcp.json，合并 managed_servers，保留用户添加的条目。

    只更新 loop 管理的 server key（UnityMCP），其余原样保留。
    文件不存在时，用 managed_servers 创建。
    """
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                old = json.load(f)
            except json.JSONDecodeError:
                print(f"  [WARN] {label} JSON 解析失败，将重新生成")
                old = {}
        old_servers = old.get("mcpServers", {})
    else:
        old_servers = {}

    # 合并：managed_servers 覆盖同名 key，用户添加的保留
    merged_servers = dict(old_servers)
    merged_servers.update(managed_servers)
    return {"mcpServers": merged_servers}


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
    agent_dir = get_agent_dir(config)

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

    src_dir = os.path.join(_get_templates_root(), "scripts")

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

    # taskhelper.py 直接从 src/loop_engineering/ 复制（无模板副本）
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_th = os.path.join(pkg_dir, "loop-engineering", "taskhelper.py")
    dst_th = os.path.join(target_dir, "taskhelper.py")
    if os.path.exists(src_th):
        if os.path.exists(dst_th):
            with open(src_th, "rb") as fs:
                src_content = fs.read()
            with open(dst_th, "rb") as fd:
                dst_content = fd.read()
            if src_content != dst_content:
                shutil.copy2(src_th, dst_th)
                print(f"  [OK] taskhelper.py 已更新 (来自 src/)")
        else:
            shutil.copy2(src_th, dst_th)
            print(f"  [OK] taskhelper.py 已部署 (来自 src/)")


def deploy_verify_docs(config):
    """从 Jinja2 模板渲染 TEST.md 到项目根目录."""
    print("--- 部署验证文档 ---")
    from jinja2 import Environment, FileSystemLoader

    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = get_agent_dir(config)
    project_type = config.get("type", "generic")

    templates_dir = os.path.join(_get_templates_root(), "verify", project_type)

    if not os.path.isdir(templates_dir):
        print(f"  WARNING: 模板目录不存在: {templates_dir}，fallback 到 generic")
        templates_dir = os.path.join(_get_templates_root(), "verify", "generic")
        if not os.path.isdir(templates_dir):
            print(f"  [FAIL] generic 模板目录也不存在，跳过验证文档部署")
            return
        project_type = "generic"

    target_dir = project_root

    # 只注入项目标识和路径，其他内容由模板自带占位符，loop-verify-init 后续定制
    vars_ = {
        "project_name": project_name,
    }

    env = Environment(loader=FileSystemLoader(templates_dir))
    for doc_name in ["TEST.md"]:
        template_file = doc_name + ".j2"
        template_path = os.path.join(templates_dir, template_file)
        if not os.path.exists(template_path):
            print(f"  WARNING: 模板不存在: {template_path}")
            continue

        template = env.get_template(template_file)
        rendered = template.render(**vars_)

        target_path = os.path.join(target_dir, doc_name)
        if os.path.exists(target_path):
            with open(target_path, "r", encoding="utf-8") as f:
                existing = f.read()
            if existing == rendered:
                print(f"  跳过 {doc_name}（内容相同）")
                continue

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"  [OK] {doc_name} 已生成: {target_path}")


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
    agent_dir = get_agent_dir(config)

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

    for fname in [".loop-engineering/loop-config.yaml"]:
        src = os.path.join(project_root, fname)
        dst = os.path.join(agent_dir, fname)
        if not os.path.exists(src):
            print(f"  跳过 {os.path.basename(fname)}（不存在）")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if _file_changed(src, dst):
            shutil.copy2(src, dst)
            print(f"  [OK] {os.path.basename(fname)} 已同步")
        else:
            print(f"  跳过 {os.path.basename(fname)}（内容相同）")

    # 清理 agent workspace 中可能残留的旧 root 级别 loop-config.yaml
    old_cfg = os.path.join(agent_dir, "loop-config.yaml")
    if os.path.exists(old_cfg):
        os.remove(old_cfg)
        print("  [OK] 清理旧 loop-config.yaml（根目录残留）")

    # 同步 git 内容（skills/commands 等已在主 worktree 提交）
    print("  同步 git 内容...")
    try:
        default_ref = get_default_branch(agent_dir)
        rc, _, _ = _run(f"git checkout --detach {default_ref}", cwd=agent_dir)
        if rc != 0:
            print(f"  [FAIL] git checkout --detach {default_ref} 失败")
        else:
            print(f"  [OK] Agent worktree 已同步到 {default_ref}")
    except Exception as e:
        print(f"  [OFFLINE] git 同步失败: {str(e)[:120]}")


def ensure_claude_rules(config):
    """按项目类型补全 CLAUDE.md 规则。

    从 templates/claude/ 读取规则模板（_base.md + <project_type>.md），
    按 marker 逐段对比目标 CLAUDE.md：
    - 新规则（marker 不存在）→ 追加
    - 已存在但内容不同 → 替换
    - 内容相同 → 跳过
    """
    import re as _re

    print("--- 补全 CLAUDE.md 规则 ---")
    project_root = config["project"]["root"]
    project_type = config.get("type", "generic")
    templates_dir = os.path.join(_get_templates_root(), "claude")
    target = os.path.join(project_root, "CLAUDE.md")

    # 收集所有模板文件
    section_files = []
    for fname in ["_base.md", f"{project_type}.md"]:
        fp = os.path.join(templates_dir, fname)
        if os.path.exists(fp):
            section_files.append(fp)

    if not section_files:
        print("  无 CLAUDE.md 规则模板，跳过")
        return

    # 读取目标 CLAUDE.md
    target_content = ""
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as f:
            target_content = f.read()

    marker_re = _re.compile(
        r'<!-- loop:rule:(\S+?)-start -->(.*?)<!-- loop:rule:\1-end -->',
        _re.DOTALL,
    )

    updated = False
    for sf in section_files:
        with open(sf, "r", encoding="utf-8") as f:
            template = f.read()
        for m in marker_re.finditer(template):
            marker = m.group(1)
            new_section = m.group(0)

            # 在目标中查找同名 marker
            pattern = _re.compile(
                rf'<!-- loop:rule:{_re.escape(marker)}-start -->.*?<!-- loop:rule:{_re.escape(marker)}-end -->',
                _re.DOTALL,
            )
            existing = pattern.search(target_content)

            if existing is None:
                # 不存在 → 追加
                if not target_content.endswith("\n"):
                    target_content += "\n"
                target_content += "\n" + new_section + "\n"
                print(f"  [+] {marker} → 新增")
                updated = True
            elif existing.group(0) != new_section:
                # 存在但不同 → 替换
                target_content = target_content.replace(existing.group(0), new_section)
                print(f"  [~] {marker} → 已更新")
                updated = True
            else:
                print(f"  跳过 {marker}（内容相同）")

    if updated:
        with open(target, "w", encoding="utf-8") as f:
            f.write(target_content)
        print(f"  [OK] CLAUDE.md 已更新")
    else:
        print("  [OK] CLAUDE.md 无需更新")



def deploy_managed_files(config):
    """重新部署所有 loop 管理的文件到 .claude/ 和 agent worktree.

    与 run_setup 的模板部署逻辑完全一致，供 UI / API 复用。
    包含：skills, commands, settings, scripts, docs, MCP, agent sync。
    """
    deploy_skills(config)
    deploy_scripts(config)
    deploy_verify_docs(config)
    generate_mcp_configs(config)
    sync_to_agent(config)


def add_unity_mcp(config):
    """添加 Unity MCP 包依赖到 Packages/manifest.json."""
    print("--- Unity MCP 依赖 ---")
    project_root = config["project"]["root"]
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = get_agent_dir(config)

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
    """部署 Claude Code skills、commands 和 settings。支持 .j2 Jinja2 模板渲染."""
    print("--- 部署 Skill 和 Command ---")
    from jinja2 import Environment, BaseLoader

    project_root = config["project"]["root"]
    templates_dir = _get_templates_root()

    # 构建 Jinja2 模板变量
    project_name = config["project"]["name"]
    agent_workspace = config["agent"]["workspace"]
    agent_dir = get_agent_dir(config)
    agent_port = config["agent"]["mcp_port"]
    agent_name = config["agent"]["name"]
    data_repo = config.get("data_repo", {})
    data_repo_path = data_repo.get("path", "")
    data_repo_name = os.path.basename(data_repo_path) if data_repo_path else ""
    agent_workspace_last = agent_workspace.replace("\\", "/").rstrip("/").split("/")[-1]

    j2_env = Environment(loader=BaseLoader())
    j2_vars = {
        "project_name": project_name,
        "project_root": project_root.replace("\\", "/"),
        "agent_workspace": agent_workspace.replace("\\", "/"),
        "agent_workspace_last": agent_workspace_last,
        "agent_dir": agent_dir.replace("\\", "/"),
        "agent_port": agent_port,
        "agent_name": agent_name,
        "data_repo_path": data_repo_path.replace("\\", "/"),
        "data_repo_name": data_repo_name,
        "has_data_repo": bool(data_repo_path),
        "default_ref": get_default_branch(project_root),
        "tasks_path": os.path.join(project_root, "tasks.md").replace("\\", "/"),
        "is_unity": config.get("type", "").startswith("unity-"),
        "project_type": config.get("type", "generic"),
    }

    # Skills
    skills_src = os.path.join(templates_dir, "skills")
    if os.path.isdir(skills_src):
        skills_dst = os.path.join(project_root, ".claude", "skills")
        for name in os.listdir(skills_src):
            skill_dir = os.path.join(skills_src, name)
            if not os.path.isdir(skill_dir):
                continue
            # Handle .j2 template files (Jinja2 rendering)
            j2_src = os.path.join(skill_dir, "SKILL.md.j2")
            md_src = os.path.join(skill_dir, "SKILL.md")
            dst = os.path.join(skills_dst, name, "SKILL.md")
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            if os.path.exists(j2_src):
                with open(j2_src, "r", encoding="utf-8") as f:
                    template_str = f.read()
                rendered = j2_env.from_string(template_str).render(**j2_vars)
                existing = ""
                if os.path.exists(dst):
                    with open(dst, "r", encoding="utf-8") as f:
                        existing = f.read()
                if existing == rendered:
                    print(f"  跳过 skill: {name}（内容相同）")
                else:
                    with open(dst, "w", encoding="utf-8") as f:
                        f.write(rendered)
                    print(f"  [OK] skill: {name}（Jinja2 渲染）")
            elif os.path.exists(md_src):
                if _file_changed(md_src, dst):
                    shutil.copy2(md_src, dst)
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

    # Verifier skills — 从 templates/verify/<type>/skills/ 复制到 .claude/skills/
    project_type = config.get("type", "generic")
    verifier_src = os.path.join(templates_dir, "verify", project_type, "skills")
    if os.path.isdir(verifier_src):
        skills_dst = os.path.join(project_root, ".claude", "skills")
        for name in os.listdir(verifier_src):
            skill_src = os.path.join(verifier_src, name)
            if not os.path.isdir(skill_src):
                continue
            src_file = os.path.join(skill_src, "SKILL.md")
            if not os.path.exists(src_file):
                continue
            dst_file = os.path.join(skills_dst, name, "SKILL.md")
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            if _file_changed(src_file, dst_file):
                shutil.copy2(src_file, dst_file)
                print(f"  [OK] verifier skill: {name}")
            else:
                print(f"  跳过 verifier skill: {name}（内容相同）")


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


def run_setup(config, force=False, share_package_cache=True):
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
        ("PackageCache 共享", lambda: share_package_cache(config)) if share_package_cache else None,
        ("部署环境脚本", lambda: deploy_scripts(config)),
        ("部署 Skill 和 Command", lambda: deploy_skills(config)),
        ("添加 Unity MCP 依赖", lambda: add_unity_mcp(config)),
        ("部署验证文档", lambda: deploy_verify_docs(config)),
        ("注册通知协议", lambda: register_protocol(config)),
        ("补全 CLAUDE.md 规则", lambda: ensure_claude_rules(config)),
        ("提交 Setup 文件", lambda: _commit_setup_files(config)),
        ("同步到 Agent Worktree", lambda: sync_to_agent(config)),
    ]
    steps = [s for s in steps if s is not None]

    # 写入配置文件（在提交步骤之前）
    clean_config = {k: v for k, v in config.items() if not k.startswith("_")}
    config_path = cfg.write_config(config["project"]["root"], clean_config)
    _ensure_gitignore(config["project"]["root"], ".loop-engineering/")

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

    print()
    print("=" * 50)
    print("[OK] Setup 完成！")
    print()
    print("接下来:")
    agent_dir = get_agent_dir(config)
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
        "TEST.md",
        "CLAUDE.md",
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


# ── Teardown ──────────────────────────────────────────────────

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
        if force and os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)
            _run("git worktree prune", cwd=source_repo)
            _log(f"移除 {label}", True, "强制删除目录 + prune")
            return
        _log(f"移除 {label}", False, stderr[:120])
    else:
        _run("git worktree prune", cwd=source_repo)
        _log(f"移除 {label}", True)


def run_teardown(project_root, force=False, dry_run=False):
    """移除 loop-engineering 的 agent worktree 和注册表条目。

    不删除主项目中的文件（.claude/、.mcp.json 等保留）。
    返回 {"removed": bool, "steps": [...], "warnings": [...]}
    """
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
