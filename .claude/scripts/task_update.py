#!/usr/bin/env python3
"""更新 tasks.md 中任务的状态 / meta / 反馈。

零依赖，纯 stdlib + task_line 共享模块。
由 loop setup 部署到 .claude/scripts/。

用法:
  python .claude/scripts/task_update.py <task_id> <status> [--project-root <dir>]
      [--append-meta <text>] [--set-meta <text>] [--add-feedback <text>]
      [--assignee <name>]

  status: ~ | x | r | ' ' (空格=待办)
  --append-meta:  追加到已有 meta（用 ' · ' 分隔）
  --set-meta:     替换 meta
  --add-feedback: 追加一条反馈缩进行
  --assignee:     限定 assignee（不传则匹配任意 assignee）

示例:
  # 标记进行中
  python .claude/scripts/task_update.py 770ea8b5 "~" --project-root D:/work_pvp/loop-engineering

  # 标记完成 + 追加运行记录
  python .claude/scripts/task_update.py 770ea8b5 x --project-root D:/work_pvp/loop-engineering --append-meta "18:30 IMP1 VFY1 PASS"

  # 标记为重新打开
  python .claude/scripts/task_update.py 770ea8b5 r --project-root D:/work_pvp/loop-engineering --add-feedback "删除文件漏了"
"""

import os
import sys

# task_line.py 在同一目录，直接 import
from task_line import update_task


def _find_project_root(start_dir=None):
    """从 start_dir 向上查找 .loop-engineering/loop-config.yaml."""
    if start_dir is None:
        start_dir = os.getcwd()
    start_dir = os.path.abspath(start_dir)
    p = start_dir
    for _ in range(10):
        if os.path.exists(os.path.join(p, ".loop-engineering", "loop-config.yaml")):
            return p
        if os.path.exists(os.path.join(p, "loop-config.yaml")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return start_dir


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if len(sys.argv) < 3:
        print("用法: task_update.py <task_id> <status> [--project-root <dir>] [--append-meta <text>] [--add-feedback <text>] [--assignee <name>]")
        sys.exit(1)

    task_id = sys.argv[1]
    status = sys.argv[2]

    # 验证 status
    if status not in (" ", "~", "x", "r"):
        print(f"错误: status 必须是 ' ', '~', 'x', 'r' 之一，收到: '{status}'")
        sys.exit(1)

    project_root = None
    append_meta = None
    set_meta = None
    add_feedback = None
    assignee = ""

    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
            i += 2
        elif arg == "--append-meta" and i + 1 < len(sys.argv):
            append_meta = sys.argv[i + 1]
            i += 2
        elif arg == "--set-meta" and i + 1 < len(sys.argv):
            set_meta = sys.argv[i + 1]
            i += 2
        elif arg == "--add-feedback" and i + 1 < len(sys.argv):
            add_feedback = sys.argv[i + 1]
            i += 2
        elif arg == "--assignee" and i + 1 < len(sys.argv):
            assignee = sys.argv[i + 1]
            i += 2
        else:
            print(f"未知参数: {arg}")
            sys.exit(1)

    if not project_root:
        project_root = _find_project_root()

    tasks_path = os.path.join(project_root, "tasks.md")
    modified, old_line, new_line = update_task(
        tasks_path, task_id,
        status=status,
        append_meta=append_meta,
        set_meta=set_meta,
        add_feedback=add_feedback,
        assignee=assignee,
    )

    if modified:
        print(f"[OK] {task_id} 状态已更新")
        print(f"  旧: {old_line}")
        print(f"  新: {new_line}")
    else:
        print(f"[FAIL] 未找到任务 {task_id}" + (f" (assignee={assignee})" if assignee else ""))
        sys.exit(1)


if __name__ == "__main__":
    main()
