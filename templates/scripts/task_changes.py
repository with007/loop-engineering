#!/usr/bin/env python3
"""扫描 OpenSpec changes 并输出 AskUserQuestion 选项 JSON。

零依赖，纯 stdlib。按修改时间倒序，取最新 4 个。

用法:
  python .claude/scripts/task_changes.py          # 输出 JSON
  python .claude/scripts/task_changes.py --count  # 输出总数
"""

import json
import os
import sys


def _find_project_root(start_dir=None):
    """从 start_dir 向上查找项目根（有 openspec/changes/ 或 loop-config.yaml）。"""
    if start_dir is None:
        start_dir = os.getcwd()
    start_dir = os.path.abspath(start_dir)
    p = start_dir
    for _ in range(10):
        if os.path.isdir(os.path.join(p, "openspec", "changes")):
            return p
        if os.path.exists(os.path.join(p, "loop-config.yaml")):
            return p
        if os.path.exists(os.path.join(p, ".loop-engineering", "loop-config.yaml")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return start_dir


def _extract_summary(proposal_path):
    """从 proposal.md 提取一行摘要（跳过 frontmatter 和标题）。"""
    try:
        with open(proposal_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    # 跳过 frontmatter (--- ... ---)
    start = 0
    in_fm = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
            else:
                start = i + 1
                break

    # 找第一个有意义的非标题行（> 15 字符）
    for line in lines[start:]:
        s = line.strip()
        if s and not s.startswith("#") and len(s) > 15:
            return s[:120]

    # 回退：第一个标题
    for line in lines[start:]:
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("# ")[:120]

    return ""


def list_changes(project_root):
    """返回 [(name, summary, mtime), ...]，按 mtime 倒序。"""
    changes_dir = os.path.join(project_root, "openspec", "changes")
    if not os.path.isdir(changes_dir):
        return []

    entries = []
    for name in os.listdir(changes_dir):
        path = os.path.join(changes_dir, name)
        if not os.path.isdir(path) or name == "archive":
            continue
        proposal = os.path.join(path, "proposal.md")
        if not os.path.isfile(proposal):
            continue
        summary = _extract_summary(proposal)
        mtime = os.path.getmtime(path)
        entries.append((name, summary, mtime))

    entries.sort(key=lambda x: x[2], reverse=True)
    return entries


def to_options(entries, max_count=4):
    """转为 AskUserQuestion options 格式。"""
    shown = entries[:max_count]
    return [
        {"label": name, "description": summary if summary else name}
        for name, summary, _mtime in shown
    ]


def main():
    project_root = _find_project_root()
    entries = list_changes(project_root)

    if "--count" in sys.argv:
        print(len(entries))
        return

    options = to_options(entries)
    output = {
        "total": len(entries),
        "shown": len(options),
        "options": options,
        "question": f"选择要添加的 OpenSpec change（共 {len(entries)} 个，显示最新 {len(options)} 个）：",
    }
    # 确保 stdout 支持 UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
