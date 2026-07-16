#!/usr/bin/env python3
"""一次性迁移: 旧 tasks.md → state.json → 全量重写 tasks.md.

薄壳 — 只包含旧格式解析（_parse_task_line_robust），其余逻辑复用 taskhelper 模块。

用法:
  python .claude/scripts/migrate_tasks.py [--project-root <dir>] [--dry-run]
"""

import argparse
import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taskhelper import find_project_root, create_state_from_old_entry, rebuild_tasks_md, parse_meta_to_runs, _state_path


# ═══════════════════════════════════════════════════════════════════════════════
# 旧格式解析（仅迁移需要 — 处理描述中的 — 字符）
# ═══════════════════════════════════════════════════════════════════════════════

_TASK_LINE_ROBUST_RE = re.compile(r'^- \[(.)\]\s+(.+)$')
_TASK_ID_RE = re.compile(r'\[([a-f0-9]{8})\]')
_ASSIGNEE_RE = re.compile(r'\(→\s*(\w+)\)')
_META_SEP_RE = re.compile(r'\s+—\s+(.+)$')


def _parse_task_line_robust(line):
    """鲁棒解析 tasks.md 行，不受描述中 — 字符影响。

    策略: 找到 [task_id] 锚点，从 task_id 之后匹配 meta —。
    TaskLine.parse 的正则无法处理描述含 — 的情况。
    """
    m = _TASK_LINE_ROBUST_RE.match(line)
    if not m:
        return None

    status = m.group(1)
    rest = m.group(2)

    tid_match = _TASK_ID_RE.search(rest)
    task_id = tid_match.group(1) if tid_match else ""

    asg_match = _ASSIGNEE_RE.search(rest)
    assignee = asg_match.group(1) if asg_match else ""

    meta = ""
    if task_id:
        tid_end = tid_match.end()
        after_tid = rest[tid_end:]
        mm = _META_SEP_RE.search(after_tid)
        if mm:
            meta = mm.group(1)

    desc = rest
    if meta and task_id:
        tid_end = tid_match.end()
        after_tid = rest[tid_end:]
        mm = _META_SEP_RE.search(after_tid)
        if mm:
            desc = rest[:tid_end + mm.start()]

    if assignee:
        desc = _ASSIGNEE_RE.sub('', desc)
    desc = _TASK_ID_RE.sub('', desc)
    desc = desc.strip()
    desc = re.sub(r'\s+—\s*$', '', desc)

    return {
        "status": status,
        "description": desc,
        "assignee": assignee,
        "task_id": task_id,
        "meta_raw": meta,
    }


def parse_old_tasks(tasks_path):
    """解析旧 tasks.md，返回按日期分组的任务列表。"""
    with open(tasks_path, 'r', encoding='utf-8') as f:
        raw = f.read()

    lines = raw.split('\n')
    date_groups = OrderedDict()
    current_date = None

    i = 0
    while i < len(lines):
        line = lines[i]

        m = re.match(r'^##\s+(\d{4}-\d{2}-\d{2})', line)
        if m:
            current_date = m.group(1)
            if current_date not in date_groups:
                date_groups[current_date] = []
            i += 1
            continue

        parsed = _parse_task_line_robust(line)
        if parsed and parsed["task_id"]:
            feedback_lines = []
            j = i + 1
            while j < len(lines) and lines[j].startswith(("  ", "\t")):
                stripped = lines[j].strip()
                if stripped:
                    feedback_lines.append(stripped)
                j += 1

            entry = {
                "task_id": parsed["task_id"],
                "description": parsed["description"],
                "assignee": parsed["assignee"],
                "status": parsed["status"],
                "meta_raw": parsed["meta_raw"],
                "feedback_lines": feedback_lines,
            }
            if current_date:
                date_groups[current_date].append(entry)
            else:
                if "unknown" not in date_groups:
                    date_groups["unknown"] = []
                date_groups["unknown"].append(entry)
            i = j
            continue

        i += 1

    return date_groups


# ═══════════════════════════════════════════════════════════════════════════════
# Main — 复用 taskhelper 的核心逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="tasks.md → state.json 迁移")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root or find_project_root()
    tasks_path = os.path.join(project_root, "tasks.md")

    if not os.path.exists(tasks_path):
        print(f"ERROR: {tasks_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Project: {project_root}")
    print(f"Tasks:   {tasks_path}")
    print()

    # Phase 1: 解析旧格式（仅此步骤需要本脚本的鲁棒解析器）
    date_groups = parse_old_tasks(tasks_path)
    total_tasks = sum(len(v) for v in date_groups.values())
    print(f"=== Phase 1: 解析 tasks.md ===")
    print(f"日期分组: {len(date_groups)}  任务总数: {total_tasks}")
    for date_str, entries in date_groups.items():
        print(f"  {date_str}: {len(entries)} tasks")
    print()

    # Phase 2+3: 创建 state.json — 复用 taskhelper
    print(f"=== Phase 2+3: 创建 state.json ===")
    if args.dry_run:
        print("[DRY RUN] 预览模式:")
    created = 0
    skipped = 0
    for date_str, entries in date_groups.items():
        for entry in entries:
            if args.dry_run:
                path = _state_path(project_root, entry["task_id"])
                if os.path.exists(path):
                    skipped += 1
                    print(f"  · {entry['task_id']}  (exists, skip)")
                else:
                    created += 1
                    runs = parse_meta_to_runs(entry["meta_raw"], date_str)
                    print(f"  ✓ {entry['task_id']}  ({len(runs)} runs)")
            else:
                ok, detail = create_state_from_old_entry(project_root, entry, date_str)
                if ok:
                    created += 1
                    print(f"  ✓ {entry['task_id']}  ({detail})")
                else:
                    skipped += 1
                    print(f"  · {entry['task_id']}  {detail}")

    print(f"\n创建: {created}  跳过: {skipped}")
    print()

    # Phase 4: 重写 tasks.md — 复用 taskhelper
    print(f"=== Phase 4: 重写 tasks.md ===")
    if args.dry_run:
        print("[DRY RUN] 跳过写入")
    else:
        new_path = rebuild_tasks_md(project_root, date_groups)
        print(f"已写入: {new_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
