#!/usr/bin/env python3
"""TaskLine — tasks.md 任务行的解析、格式化、状态修改（共享模块）。

零依赖，纯 stdlib。由 task_pick.py、task_done.py、task_update.py 共用。
由 loop setup 部署到 .claude/scripts/。
"""

import re

_TASK_LINE_RE = re.compile(
    r'^- \[(.)\]\s+'             # checkbox: - [x]
    r'(.+?)'                      # description (non-greedy)
    r'(?:\s+\(→\s*(\w+)\))?'     # optional assignee: (→ whoami)
    r'(?:\s+\[([a-f0-9]{8})\])?' # optional task_id: [xxxxxxxx]
    r'(?:\s+—\s+(.+))?'          # optional meta: — text
    r'$'
)


class TaskLine:
    """tasks.md 中单行任务的解析、格式化、状态修改."""

    __slots__ = ("status", "description", "assignee", "task_id", "meta", "feedback")

    def __init__(self, status=" ", description="", assignee="", task_id="", meta="", feedback=None):
        self.status = status
        self.description = description
        self.assignee = assignee
        self.task_id = task_id
        self.meta = meta
        self.feedback = feedback if feedback is not None else []

    # ── 解析 / 格式化 ──

    @classmethod
    def parse(cls, line):
        m = _TASK_LINE_RE.match(line)
        if not m:
            return None
        return cls(
            status=m.group(1),
            description=m.group(2).strip(),
            assignee=m.group(3) or "",
            task_id=m.group(4) or "",
            meta=m.group(5) or "",
        )

    def format(self):
        parts = [f"- [{self.status}] {self.description}"]
        if self.assignee:
            parts.append(f" (→ {self.assignee})")
        if self.task_id:
            parts.append(f" [{self.task_id}]")
        if self.meta:
            parts.append(f" — {self.meta}")
        return "".join(parts)

    # ── 状态修改 ──

    def update_status(self, new_status):
        """修改状态字符: ' ' → '~' → 'x' → 'r'."""
        self.status = new_status

    # ── Meta 操作 ──

    def set_meta(self, text):
        """替换 meta 文本."""
        self.meta = text

    def append_meta(self, text):
        """追加 meta 文本（用 ' · ' 分隔）."""
        if self.meta:
            self.meta += " · " + text
        else:
            self.meta = text

    # ── 反馈操作 ──

    def add_feedback(self, text):
        """追加一条反馈缩进行."""
        self.feedback.append(text)

    def clear_feedback(self):
        """清空所有反馈."""
        self.feedback = []

    def format_feedback(self):
        """格式化反馈为缩进行列表."""
        return [f"  {line}" for line in self.feedback]


# ── 工具函数 ──

def load_tasks(tasks_path):
    """读取 tasks.md，返回 [(TaskLine|None, raw_line), ...] 列表.

    None 表示非任务行或解析失败的行。保留原始行内容以支持写回。
    """
    try:
        with open(tasks_path, 'r', encoding='utf-8') as f:
            lines = f.read().split('\n')
    except FileNotFoundError:
        return []

    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        tl = TaskLine.parse(line)
        if tl:
            # 收集缩进反馈行
            i += 1
            while i < len(lines) and lines[i].startswith(("  ", "\t")):
                tl.feedback.append(lines[i].strip())
                i += 1
            result.append((tl, line))
            continue
        result.append((None, line))
        i += 1
    return result


def save_tasks(tasks_path, entries):
    """将 [(TaskLine|None, raw_line), ...] 写回 tasks.md."""
    output = []
    for tl, raw in entries:
        if tl:
            output.append(tl.format())
            output.extend(tl.format_feedback())
        else:
            output.append(raw)
    with open(tasks_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))


def find_task(entries, task_id, assignee=""):
    """在 load_tasks 返回的 entries 中查找匹配的任务，返回 (index, TaskLine)."""
    for i, (tl, _raw) in enumerate(entries):
        if tl and tl.task_id == task_id:
            if not assignee or tl.assignee == assignee:
                return i, tl
    return None, None


def update_task(tasks_path, task_id, status=None, append_meta=None, set_meta=None,
                add_feedback=None, assignee="", if_status_in=None):
    """更新 tasks.md 中匹配 task_id 的任务行，保留其他行不变.

    Args:
        tasks_path: tasks.md 路径
        task_id: 要修改的任务 ID
        status: 新状态字符 (' ', '~', 'x', 'r')，None 表示不改
        append_meta: 追加的 meta 文本
        set_meta: 替换的 meta 文本（优先级高于 append_meta）
        add_feedback: 追加的反馈文本
        assignee: 可选，限定 assignee
        if_status_in: 可选，当前状态必须在此集合中才修改（如 (" ", "~", "r")）

    Returns:
        (modified, old_line, new_line) — modified 为 True 表示已修改
    """
    entries = load_tasks(tasks_path)
    idx, tl = find_task(entries, task_id, assignee)
    if tl is None:
        return False, "", ""

    if if_status_in is not None and tl.status not in if_status_in:
        return False, "", ""

    old_line = tl.format()

    if status is not None:
        tl.update_status(status)
    if set_meta is not None:
        tl.set_meta(set_meta)
    elif append_meta is not None:
        tl.append_meta(append_meta)
    if add_feedback is not None:
        tl.add_feedback(add_feedback)

    save_tasks(tasks_path, entries)
    return True, old_line, tl.format()
