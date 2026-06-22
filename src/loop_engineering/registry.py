"""Loop Engineering 项目注册表.

记录所有已知项目，支持 Dashboard 多项目切换。
存储位置: ~/.config/loop-engineering/projects.yaml
"""

import os
import yaml


def _registry_path():
    """注册表文件路径."""
    base = os.environ.get("LOOP_REGISTRY", os.path.join(os.path.expanduser("~"), ".config", "loop-engineering"))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "projects.yaml")


def list_projects():
    """列出所有已注册项目."""
    path = _registry_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("projects", [])


def get_project(root):
    """获取单个项目."""
    for p in list_projects():
        if p["root"] == root:
            return p
    return None


def register_project(root, name=None):
    """注册一个项目."""
    root = os.path.abspath(root)
    name = name or os.path.basename(root)

    projects = list_projects()
    # 去重
    projects = [p for p in projects if p["root"] != root]
    projects.append({"name": name, "root": root})

    _save(projects)
    return {"name": name, "root": root}


def remove_project(root):
    """移除一个项目."""
    projects = [p for p in list_projects() if p["root"] != root]
    _save(projects)


def _save(projects):
    with open(_registry_path(), "w", encoding="utf-8") as f:
        yaml.dump({"projects": projects}, f, allow_unicode=True, default_flow_style=False)
