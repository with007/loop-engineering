"""Loop Engineering 配置管理.

读取和写入 loop-config.yaml，自动检测项目设置。
"""

import os
import platform
import subprocess
import re
from pathlib import Path

import yaml

# 默认配置
DEFAULT_CONFIG = {
    "agent": {
        "name": None,          # 自动检测: git config user.name
        "workspace": None,     # 自动检测: 项目同级目录 + "-agent"
        "mcp_port": 9080,
    },
    "main": {
        "mcp_port": 8080,
    },
    # data_repo 可选
}


def _run(cmd, cwd=None):
    """运行 shell 命令，返回 (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=30
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception:
        return -1, "", ""


def read_config(project_root):
    """读取项目根目录下的 loop-config.yaml，返回 dict.

    如果文件不存在，返回空 dict。
    """
    config_path = os.path.join(project_root, "loop-config.yaml")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_config(project_root, config):
    """写入 loop-config.yaml 到项目根目录."""
    config_path = os.path.join(project_root, "loop-config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return config_path


def detect_config(project_root):
    """自动检测项目设置，返回建议的配置 dict.

    检测项:
    - 项目名称: 从目录名推断
    - Git repo: git rev-parse --show-toplevel
    - Unity 工程: ProjectSettings/ 目录存在
    - 已有 MCP 端口: 解析 .mcp.json
    - Agent workspace: 自动推断（项目同级目录 + "-agent"）
    - Git 用户名: git config user.name
    """
    project_root = os.path.abspath(project_root)
    project_name = os.path.basename(project_root)

    detected = {
        "project": {
            "name": project_name,
            "root": project_root,
        },
        "agent": {
            "name": _detect_git_user(project_root),
            "workspace": _detect_workspace(project_root, project_name),
            "mcp_port": DEFAULT_CONFIG["agent"]["mcp_port"],
        },
        "main": {
            "mcp_port": _detect_mcp_port(project_root),
        },
    }

    # 检测 Unity 工程
    if os.path.isdir(os.path.join(project_root, "ProjectSettings")):
        detected["_detected"] = detected.get("_detected", {})
        detected["_detected"]["unity"] = True
        # 检查是否有 .mcp.json 在 ProjectSettings 下
        mcp_project = os.path.join(project_root, "ProjectSettings", "McpProjectConfig.json")
        if os.path.exists(mcp_project):
            detected["_detected"]["mcp_project_config"] = True

    # 检测 data repo
    data_repo = _detect_data_repo(project_root, project_name)
    if data_repo:
        detected["data_repo"] = {"path": data_repo}

    return detected


def _detect_workspace(project_root, project_name):
    """推断 agent workspace 路径.

    优先: grandparent/<parent-dir>-agent (如 d:/work_pvp/pvp8-agent)
    回退: parent/<project>-agent (如 d:/work_pvp/MyProject-agent)
    """
    parent = os.path.dirname(project_root)          # d:/work_pvp/pvp8
    grandparent = os.path.dirname(parent)            # d:/work_pvp
    parent_name = os.path.basename(parent)           # pvp8

    # 优先: grandparent/<parent-dir>-agent
    candidate = os.path.join(grandparent, parent_name + "-agent")
    if os.path.exists(candidate):
        return candidate

    # 回退: parent/<project>-agent
    fallback = os.path.join(parent, project_name + "-agent")
    return fallback


def _detect_mcp_port(project_root):
    """从 .mcp.json 解析 MCP 端口，默认 8080."""
    mcp_path = os.path.join(project_root, ".mcp.json")
    if os.path.exists(mcp_path):
        try:
            import json
            with open(mcp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            url = data.get("mcpServers", {}).get("UnityMCP", {}).get("url", "")
            m = re.search(r":(\d+)/", url)
            if m:
                return int(m.group(1))
        except Exception:
            pass
    return DEFAULT_CONFIG["main"]["mcp_port"]


def _detect_git_user(project_root):
    """检测 git config user.name."""
    code, stdout, _ = _run("git config user.name", cwd=project_root)
    if code == 0 and stdout:
        return stdout
    return None


def _detect_data_repo(project_root, project_name):
    """检测数据配表仓库.

    常见模式：
    - project_root = d:/work_pvp/pvp8/PVPProject8
    - data_repo = d:/work_pvp/PVPProject8Data (project_root 上一个层级 + Data)
    """
    parent = os.path.dirname(project_root)
    # 去掉最后一个目录，在同级找 +Data
    candidate = os.path.join(os.path.dirname(parent), project_name + "Data")
    if os.path.isdir(os.path.join(candidate, ".git")):
        return candidate
    # 也试 PVPProject8Data (项目名 + Data)
    candidate2 = os.path.join(os.path.dirname(parent), project_name + "Data")
    if candidate2 != candidate and os.path.isdir(os.path.join(candidate2, ".git")):
        return candidate2
    return None
