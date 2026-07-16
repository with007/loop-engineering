#!/usr/bin/env python3
"""统一任务状态管理。纯 stdlib，部署时复制到 .claude/scripts/。

用法:
  python taskhelper.py init --desc "..." --assignee <name> [--project-root <dir>]
  python taskhelper.py pick <whoami> [--project-root <dir>]
  python taskhelper.py status <task_id> <~|x|r| > [--project-root <dir>]
  python taskhelper.py phase <task_id> [<str>|--clear] [--project-root <dir>]
  python taskhelper.py run-start <task_id> [--project-root <dir>]
  python taskhelper.py run-done <task_id> --result pass|fail [--do-commit] [--project-root <dir>]
  python taskhelper.py get-phase [--project-root <dir>]
  python taskhelper.py feedback <task_id> <text> [--project-root <dir>]
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import yaml
from datetime import datetime, timezone

# ── TaskLine: tasks.md 任务行的解析、格式化、状态修改 ──

_TASK_LINE_RE = re.compile(
    r'^- \[(.)\]\s+'             # checkbox: - [x]
    r'(.+?)'                      # description (non-greedy)
    r'(?:\s+\(→\s*(\w+)\))?'     # optional assignee: (→ whoami)
    r'(?:\s+\[([a-f0-9]{8})\])?' # optional task_id: [xxxxxxxx]
    r'(?:\s+—\s+(.+))?'          # optional meta: — text
    r'$'
)

# 匹配缩进行（2+ 空格后接非空白字符），用于识别任务反馈行
FEEDBACK_LINE_RE = re.compile(r'^\s{2,}\S')


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

    def __repr__(self):
        fields = [f"status={self.status!r}"]
        if self.description:
            fields.append(f"description={self.description!r}")
        if self.assignee:
            fields.append(f"assignee={self.assignee!r}")
        if self.task_id:
            fields.append(f"task_id={self.task_id!r}")
        if self.meta:
            fields.append(f"meta={self.meta!r}")
        return f"TaskLine({', '.join(fields)})"

    def __eq__(self, other):
        if not isinstance(other, TaskLine):
            return NotImplemented
        return (self.status == other.status and
                self.description == other.description and
                self.assignee == other.assignee and
                self.task_id == other.task_id and
                self.meta == other.meta)

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
            if tl.feedback:
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


def replace_task(entries, task_id, new_taskline):
    """在 entries 中找到 task_id 对应的 TaskLine 并替换，未找到则追加到末尾。"""
    for i, (tl, _) in enumerate(entries):
        if tl and tl.task_id == task_id:
            entries[i] = (new_taskline, "")
            return
    entries.append((new_taskline, ""))


def find_project_root(start_dir=None):
    """从 start_dir 向上查找项目根（有 .loop-engineering/loop-config.yaml 或 loop-config.yaml）."""
    return _find_project_root(start_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def _run(cmd, input_text=None):
    """运行 shell 命令，返回 CompletedProcess。"""
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        encoding='utf-8', errors='replace', input=input_text,
    )


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _task_id(desc):
    """从描述生成 8 位 task ID（md5 前 8 位）。"""
    return hashlib.md5(desc.encode()).hexdigest()[:8]


def _make_readable_slug(description, max_len=40):
    """从描述生成可读的 git 分支名后缀。"""
    desc = re.split(r'\s+—\s+', description.strip())[0].strip()
    desc = re.sub(r'[\\:?*\[\]~^{}!]', '', desc)
    desc = re.sub(r'\s+', '-', desc)
    desc = re.sub(r'-{2,}', '-', desc)
    desc = re.sub(r'\.{2,}', '', desc)
    desc = re.sub(r'^\.|\.$', '', desc)
    desc = re.sub(r'^-+|-+$', '', desc)
    result = desc[:max_len]
    return result if len(result) >= 1 else 'task'


def _make_branch_name(whoami, task_id, description):
    slug = _make_readable_slug(description)
    return f"agent/{whoami}/{task_id}-{slug}"


def _find_project_root(start_dir=None):
    """向上查找项目根（有 .loop-engineering/loop-config.yaml）。"""
    p = os.path.abspath(start_dir or os.getcwd())
    for _ in range(10):
        if os.path.exists(os.path.join(p, ".loop-engineering", "loop-config.yaml")):
            return p
        if os.path.exists(os.path.join(p, "loop-config.yaml")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.path.abspath(start_dir or os.getcwd())


# ═══════════════════════════════════════════════════════════════════════════════
# 旧格式迁移
# ═══════════════════════════════════════════════════════════════════════════════

META_ENTRY_RE = re.compile(
    r'(\d{1,2}:\d{2})?\s*IMP(\d+)\s+VFY(\d+)\s+(PASS|FAIL)'
)
FEEDBACK_HEADER_RE = re.compile(r'^##\s+IMP(\d+)\s*反馈')


def parse_meta_to_runs(meta_raw, date_str):
    """将旧格式 meta 字符串解析为 runs 列表。

    meta 格式: `15:42 IMP1 VFY1 PASS · 16:45 IMP2 VFY1 PASS`
    每个 `IMP{n} VFY{m} RESULT` (可选前导时间) 为一个 run 条目。
    """
    if not meta_raw:
        return []

    runs = []
    for m in META_ENTRY_RE.finditer(meta_raw):
        time_str = m.group(1)       # e.g. "15:42" or None
        imp_round = int(m.group(2))
        vfy_round = int(m.group(3))
        result = m.group(4).lower()  # "pass" or "fail"

        started_at = None
        if time_str and date_str and date_str != "unknown":
            started_at = f"{date_str}T{time_str}:00Z"

        runs.append({
            "started_at": started_at,
            "completed_at": None,
            "result": result,
            "start_round": imp_round,
            "end_round": vfy_round,
            "user_feedback": "",
            "outputs": None,
        })

    return runs


def parse_feedback_to_runs(feedback_lines):
    """将反馈行按 ## IMP{N} 分配到 run 条目。保留标题头。

    返回: {run_index: feedback_text_with_header, ...}  (0-indexed)
    """
    feedback_by_run = {}
    current_run_idx = None
    current_header = None
    current_lines = []

    for line in feedback_lines:
        m = FEEDBACK_HEADER_RE.match(line)
        if m:
            if current_run_idx is not None and current_header:
                text = current_header + "\n" + "\n".join(current_lines).strip()
                feedback_by_run[current_run_idx] = text.strip()
            current_run_idx = int(m.group(1)) - 1  # IMP1 → run[0]
            current_header = line
            current_lines = []
        elif current_run_idx is not None:
            current_lines.append(line)

    if current_run_idx is not None and current_header:
        text = current_header + "\n" + "\n".join(current_lines).strip()
        feedback_by_run[current_run_idx] = text.strip()

    return feedback_by_run


def create_state_from_old_entry(project_root, entry, date_str):
    """从旧 tasks.md 条目创建 state.json。已存在则跳过。

    entry 字段: task_id, description, assignee, status, meta_raw, feedback_lines
    返回 (created: bool, detail: str).
    """
    task_id = entry["task_id"]
    path = _state_path(project_root, task_id)
    if os.path.exists(path):
        return False, "skipped (exists)"

    runs = parse_meta_to_runs(entry.get("meta_raw", ""), date_str)
    feedback_map = parse_feedback_to_runs(entry.get("feedback_lines", []))

    for run_idx, fb_text in feedback_map.items():
        if run_idx < len(runs):
            runs[run_idx]["user_feedback"] = fb_text
        else:
            runs.append({
                "started_at": None, "completed_at": None, "result": None,
                "start_round": run_idx + 1, "end_round": None,
                "user_feedback": fb_text, "outputs": None,
            })

    if not runs and entry.get("feedback_lines"):
        runs.append({
            "started_at": None, "completed_at": None,
            "result": "pass" if entry.get("status") == "x" else None,
            "start_round": 1, "end_round": None,
            "user_feedback": "\n".join(entry["feedback_lines"]),
            "outputs": None,
        })

    created_at = f"{date_str}T00:00:00Z" if date_str and date_str != "unknown" else None

    state = {
        "task_id": task_id,
        "desc": entry["description"],
        "assignee": entry["assignee"],
        "created_at": created_at,
        "status": entry.get("status", " "),
        "phase": None,
        "runs": runs,
    }

    save_state(project_root, task_id, state)
    return True, f"{len(runs)} runs"


def rebuild_tasks_md(project_root, date_groups):
    """从 date_groups + state.json 重建 tasks.md。

    date_groups: OrderedDict of {date_str: [entry_dict, ...]}
    entry_dict 至少需要 task_id, description, assignee, status.
    """
    tasks_path = os.path.join(project_root, "tasks.md")

    lines = [
        "# Tasks",
        "",
        "> 约定: 状态和详情见 Web 面板。本文由 state.json 自动生成，勿手动编辑。",
        "",
    ]

    for date_str, entries in date_groups.items():
        lines.append(f"## {date_str}")
        lines.append("")
        for entry in entries:
            tl = TaskLine(
                status=entry.get("status", " "),
                description=entry["description"],
                assignee=entry.get("assignee", ""),
                task_id=entry["task_id"],
            )
            lines.append(tl.format())
            # 从 state.json 取反馈行
            state = load_state(project_root, entry["task_id"])
            if state:
                for run in state.get("runs", []):
                    fb = run.get("user_feedback", "")
                    if fb:
                        for line in fb.split("\n"):
                            lines.append(f"  {line.strip()}")
        lines.append("")

    with open(tasks_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return tasks_path


# ═══════════════════════════════════════════════════════════════════════════════
# state.json 读写
# ═══════════════════════════════════════════════════════════════════════════════

def _tasks_dir(project_root):
    return os.path.join(project_root, ".loop-engineering", "tasks")


def _agent_task_dir(project_root, task_id):
    """从 loop-config.yaml 提取 agent.workspace，返回 agent worktree 的任务目录路径。
    无 agent 配置时返回 None。"""
    for name in [".loop-engineering/loop-config.yaml", "loop-config.yaml"]:
        path = os.path.join(project_root, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        agent_ws = (cfg.get("agent") or {}).get("workspace", "")
        if agent_ws:
            return agent_ws.replace("\\", "/") + "/loop-engineering/.loop-engineering/tasks/" + task_id
    return None


def _state_path(project_root, task_id):
    return os.path.join(_tasks_dir(project_root), task_id, "state.json")


def load_state(project_root, task_id):
    """读取 state.json，不存在返回 None。"""
    path = _state_path(project_root, task_id)
    if not os.path.exists(path):
        # 尝试从 tasks.md 初始化
        return _init_state_from_md(project_root, task_id)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_state(project_root, task_id, state):
    """写入 state.json（自动创建目录）。"""
    task_dir = os.path.dirname(_state_path(project_root, task_id))
    os.makedirs(task_dir, exist_ok=True)
    with open(_state_path(project_root, task_id), 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _init_state_from_md(project_root, task_id):
    """从 tasks.md 解析创建最小 state.json。未匹配返回 None。"""
    tasks_path = os.path.join(project_root, "tasks.md")
    entries = load_tasks(tasks_path)
    for tl, _ in entries:
        if tl and tl.task_id == task_id:
            state = {
                "task_id": task_id,
                "desc": tl.description,
                "assignee": tl.assignee,
                "created_at": None,       # 从 tasks.md 恢复，创建时间未知
                "phase": None,
                "runs": [],
            }
            if tl.feedback:
                state["runs"].append({
                    "started_at": None,
                    "completed_at": None,  # 从 tasks.md 恢复，执行详情未知
                    "result": "pass" if tl.status == "x" else None,
                    "start_round": 1,
                    "end_round": None,
                    "user_feedback": "\n".join(tl.feedback),
                    "outputs": {},
                })
            save_state(project_root, task_id, state)
            return state
    return None


def find_active_phase(project_root):
    """遍历所有已有 state.json，返回 (task_id, phase_str) 或 (None, None)。"""
    tasks_dir = _tasks_dir(project_root)
    if not os.path.isdir(tasks_dir):
        return None, None
    for tid in os.listdir(tasks_dir):
        path = _state_path(project_root, tid)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            continue
        if state.get("phase"):
            return tid, state["phase"]
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# tasks.md 块级同步
# ═══════════════════════════════════════════════════════════════════════════════

def get_feedback_lines(runs):
    """从 runs 列表提取反馈行，自动加 ## IMP{N} 反馈 标题头。

    只处理有 user_feedback 的 run，按出现顺序编号。
    返回扁平字符串列表，可直接赋值给 TaskLine.feedback。
    """
    lines = []
    imp_n = 0
    for run in runs:
        fb = run.get("user_feedback", "")
        if fb:
            imp_n += 1
            lines.append(f"## IMP{imp_n} 反馈")
            for line in fb.split("\n"):
                lines.append(line.strip())
    return lines


def sync_tasks_md(project_root, task_id):
    """从 state.json 同步 tasks.md 中对应任务的块。"""
    state = load_state(project_root, task_id)
    if not state:
        return

    tasks_path = os.path.join(project_root, "tasks.md")
    entries = load_tasks(tasks_path)

    # 构建新的 TaskLine
    tl = TaskLine(
        status=state.get("status", " "),
        description=state.get("desc", ""),
        assignee=state.get("assignee", ""),
        task_id=task_id,
    )

    # 反馈行
    tl.feedback = get_feedback_lines(state.get("runs", []))

    # 替换或追加
    replace_task(entries, task_id, tl)
    save_tasks(tasks_path, entries)


def _ensure_state(project_root, task_id):
    """确保 state.json 存在。不存在则从 tasks.md 解析创建。"""
    if not os.path.exists(_state_path(project_root, task_id)):
        _init_state_from_md(project_root, task_id)


def _ensure_all_states(project_root):
    """遍历 tasks.md，为所有缺 state.json 的任务创建最小 state.json。"""
    tasks_path = os.path.join(project_root, "tasks.md")
    if not os.path.exists(tasks_path):
        return
    entries = load_tasks(tasks_path)
    for tl, _ in entries:
        if tl and tl.task_id:
            _ensure_state(project_root, tl.task_id)


def list_tasks(project_root):
    """从 state.json 获取任务列表（含 git 分支合并状态）。

    返回 dict 列表，字段: task_id, description, status, assignee, meta, feedback,
    created_at, phase, run_count.
    """
    _ensure_all_states(project_root)

    # Git 分支收集（从 parse_tasks 移植）
    agent_branches = _collect_agent_branches(project_root)

    result = []
    tasks_dir = _tasks_dir(project_root)
    if not os.path.isdir(tasks_dir):
        return result

    for tid in sorted(os.listdir(tasks_dir)):
        state = load_state(project_root, tid)
        if not state:
            continue

        status_char = state.get("status", " ")
        # Git 分支合并检测
        if status_char == "x" and tid in agent_branches:
            branch = agent_branches[tid]
            if _is_branch_merged(branch, project_root):
                status = "done"
            else:
                status = "pending_merge"
        else:
            s = {" ": "pending", "~": "in_progress", "x": "done", "r": "reopen"}
            status = s.get(status_char, "pending")

        # 反馈行
        feedback = get_feedback_lines(state.get("runs", []))

        result.append({
            "task_id": tid,
            "description": state.get("desc", ""),
            "status": status,
            "assignee": state.get("assignee", ""),
            "meta": "",                                     # meta 已在 state.json 中不保留
            "feedback": feedback,
            "created_at": state.get("created_at"),
            "phase": state.get("phase"),
            "run_count": len(state.get("runs", [])),
        })

    return result


def _collect_agent_branches(project_root):
    """收集 agent 分支名，按 task_id 索引。"""
    def _extract_tid(name):
        basename = name.split('/')[-1].strip()
        if re.match(r'^[a-f0-9]{8}$', basename):
            return basename
        parts = basename.split('-', 1)
        return parts[0] if parts[0] else None

    branches = {}
    try:
        r = _run('git branch --list "agent/*"')
        for line in r.stdout.strip().split("\n"):
            b = line.strip().lstrip("*+ ")
            if b:
                tid = _extract_tid(b)
                if tid and tid not in branches:
                    branches[tid] = b
    except Exception:
        pass

    try:
        r = _run('git branch -r --list "origin/agent/*"')
        for line in r.stdout.strip().split("\n"):
            b = line.strip()
            if b:
                tid = _extract_tid(b)
                if tid and tid not in branches:
                    branches[tid] = b
    except Exception:
        pass

    return branches


def _is_branch_merged(branch, project_root):
    """检查分支是否已合入 master。"""
    try:
        r = _run(f"git branch --merged origin/master | grep -E '(^|\\s){branch}$'")
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# 命令实现
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_init(project_root, desc, assignee):
    """创建新任务：state.json + tasks.md 块。"""
    tid = _task_id(desc)
    state = {
        "task_id": tid,
        "desc": desc,
        "assignee": assignee,
        "created_at": _now_iso(),
        "status": " ",
        "phase": None,
        "runs": [],
    }
    save_state(project_root, tid, state)
    sync_tasks_md(project_root, tid)
    print(f"taskID={tid}")


def cmd_pick(project_root, whoami):
    """选下一个待办任务。"""
    _ensure_all_states(project_root)
    tasks_path = os.path.join(project_root, "tasks.md")
    entries = load_tasks(tasks_path)

    tasks = [(tl, _) for tl, _ in entries if tl and tl.assignee == whoami]

    # BUSY 检查
    for tl, _ in tasks:
        if tl.status == "~":
            print("BUSY")
            return

    for tl, _ in tasks:
        if tl.status not in (" ", "r"):
            continue
        if not tl.task_id:
            continue

        desc = tl.description
        task_id = tl.task_id
        is_reopen = tl.status == "r"

        if is_reopen:
            r = _run(f"git branch -a --list 'agent/{whoami}/{task_id}-*' --sort=-committerdate")
            branches = [b.strip().lstrip('* ') for b in r.stdout.strip().split('\n') if b.strip()]
            if branches:
                branch = branches[0]
                if branch.startswith('remotes/origin/'):
                    branch = branch[len('remotes/origin/'):]
            else:
                expected = _make_branch_name(whoami, task_id, desc)
                r3 = _run(f"git reflog origin/{expected} --format=%H -1")
                if r3.returncode == 0 and r3.stdout.strip():
                    old_hash = r3.stdout.strip()
                    r4 = _run(f"git fetch origin {old_hash}")
                    if r4.returncode == 0:
                        _run(f"git branch {expected} {old_hash}")
                        branch = expected
                        print(f"NOTE: [r] task {task_id} — branch recovered from reflog ({old_hash[:8]})",
                              file=sys.stderr)
                    else:
                        print(f"WARNING: [r] task {task_id} — reflog found {old_hash[:8]} but fetch failed, skipping.",
                              file=sys.stderr)
                        continue
                else:
                    # 分支完全无法恢复 → 回退到新建分支（保留 reopen flag 传递用户反馈）
                    branch = expected
                    print(f"NOTE: [r] task {task_id} — branch unrecoverable, starting fresh",
                          file=sys.stderr)
        else:
            branch = _make_branch_name(whoami, task_id, desc)

        open_spec = "true" if (
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{desc}")) or
            os.path.isdir(os.path.join(project_root, f"openspec/changes/{task_id}"))
        ) else "false"
        reopen_flag = "true" if is_reopen else "false"

        # user_feedback: 取最近一次 run 的 feedback
        state = load_state(project_root, task_id)
        user_feedback = ""
        if state:
            runs = state.get("runs", [])
            active = next((r for r in runs if r.get("completed_at") is None), None)
            last = runs[-1] if runs else None
            fb_source = active or last
            if fb_source and fb_source.get("user_feedback"):
                user_feedback = fb_source["user_feedback"]

        parts = [f"taskID={task_id}",
                 f"branch={branch}",
                 f"desc={desc}",
                 f"openSpec={open_spec}",
                 f"reopen={reopen_flag}",
                 f"user_feedback={shlex.quote(user_feedback)}"]
        print(" ".join(parts))
        return

    print("NONE")


def cmd_status(project_root, task_id, status):
    """更新任务状态，同步 tasks.md。"""
    state = load_state(project_root, task_id)
    if not state:
        print(f"ERROR: task {task_id} not found", file=sys.stderr)
        sys.exit(1)
    state["status"] = status
    save_state(project_root, task_id, state)
    sync_tasks_md(project_root, task_id)
    print(f"[OK] {task_id} → [{status}]")


def cmd_phase(project_root, task_id, phase_str, clear):
    """读写 phase。"""
    if clear:
        state = load_state(project_root, task_id)
        if state:
            state["phase"] = None
            save_state(project_root, task_id, state)
            print("[OK] phase cleared")
        return

    if phase_str:
        state = load_state(project_root, task_id)
        if not state:
            print(f"ERROR: task {task_id} not found", file=sys.stderr)
            sys.exit(1)
        state["phase"] = phase_str
        save_state(project_root, task_id, state)
        print(f"[OK] phase={phase_str}")
    else:
        # 读取当前 phase
        state = load_state(project_root, task_id)
        if state and state.get("phase"):
            print(state["phase"])
        else:
            print("NO_PHASE")


def cmd_run_start(project_root, task_id):
    """记录 run 开始。"""
    state = load_state(project_root, task_id)
    if not state:
        print(f"ERROR: task {task_id} not found", file=sys.stderr)
        sys.exit(1)

    # 计算 start_round：扫描现有输出文件取最大轮次 +1
    task_dir = os.path.join(_tasks_dir(project_root), task_id)
    existing = glob.glob(os.path.join(task_dir, "imp-output-r*.md")) + \
               glob.glob(os.path.join(task_dir, "vfy-output-r*.md"))
    nums = []
    for f in existing:
        m = re.search(r'-r(\d+)\.md$', os.path.basename(f))
        if m:
            nums.append(int(m.group(1)))
    start_round = max(nums) + 1 if nums else 1

    # 取最新 user_feedback
    runs = state.get("runs", [])
    user_feedback = ""
    if runs and runs[-1].get("user_feedback"):
        user_feedback = runs[-1]["user_feedback"]

    run = {
        "started_at": _now_iso(),
        "completed_at": None,
        "result": None,
        "start_round": start_round,
        "end_round": None,
        "user_feedback": user_feedback,
        "outputs": None,
    }
    runs.append(run)
    state["runs"] = runs
    state["status"] = "~"
    save_state(project_root, task_id, state)
    sync_tasks_md(project_root, task_id)
    print(f"start_round={start_round}")


def cmd_run_done(project_root, task_id, result, do_commit):
    """完成当前 run。"""
    state = load_state(project_root, task_id)
    if not state:
        print(f"ERROR: task {task_id} not found", file=sys.stderr)
        sys.exit(1)

    runs = state.get("runs", [])
    if not runs:
        print("ERROR: no active run", file=sys.stderr)
        sys.exit(1)

    run = runs[-1]
    run["completed_at"] = _now_iso()
    run["result"] = result

    # 扫描输出文件（只收集 >= start_round 的本轮文件）
    task_dir = os.path.join(_tasks_dir(project_root), task_id)
    os.makedirs(task_dir, exist_ok=True)
    start_round = run["start_round"]

    # 从 agent worktree 同步输出文件到主 worktree（子代理可能在 agent worktree 写入）
    agent_dir = _agent_task_dir(project_root, task_id)
    if agent_dir and os.path.isdir(agent_dir):
        for pattern in ["imp-output-r*.md", "vfy-output-r*.md"]:
            for src in glob.glob(os.path.join(agent_dir, pattern)):
                dst = os.path.join(task_dir, os.path.basename(src))
                if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                    shutil.copy2(src, dst)

    all_imp = sorted(glob.glob(os.path.join(task_dir, "imp-output-r*.md")))
    all_vfy = sorted(glob.glob(os.path.join(task_dir, "vfy-output-r*.md")))

    def _round_num(path):
        m = re.search(r'-r(\d+)\.md$', os.path.basename(path))
        return int(m.group(1)) if m else 0

    imp_files = [f for f in all_imp if _round_num(f) >= start_round]
    vfy_files = [f for f in all_vfy if _round_num(f) >= start_round]
    run["outputs"] = {
        "imp": [os.path.basename(f) for f in imp_files],
        "vfy": [os.path.basename(f) for f in vfy_files],
    }
    if imp_files or vfy_files:
        run["end_round"] = max(
            max([_round_num(f) for f in imp_files]) if imp_files else start_round,
            max([_round_num(f) for f in vfy_files]) if vfy_files else start_round,
        )
    else:
        run["end_round"] = start_round - 1  # 没有输出，标记为无效轮次

    if result == "pass":
        state["status"] = "x"
    else:
        state["status"] = "r"

    save_state(project_root, task_id, state)
    sync_tasks_md(project_root, task_id)

    # commit + push
    if do_commit and result == "pass":
        _do_commit_push(project_root, task_id, state)

    print(f"[OK] {task_id} → {result}")


def cmd_get_phase(project_root):
    """找活跃 phase。"""
    tid, phase_str = find_active_phase(project_root)
    if tid:
        print(f"PHASE={phase_str} TASK_ID={tid}")
    else:
        print("NO_PHASE")


def cmd_feedback(project_root, task_id, text):
    """追加反馈到当前 run。"""
    state = load_state(project_root, task_id)
    if not state:
        print(f"ERROR: task {task_id} not found", file=sys.stderr)
        sys.exit(1)

    runs = state.get("runs", [])
    if not runs:
        runs.append({
            "started_at": None,
            "completed_at": None,
            "result": None,
            "start_round": 1,
            "end_round": None,
            "user_feedback": None,
            "outputs": None,
        })
        state["runs"] = runs

    run = runs[-1]
    existing = run.get("user_feedback") or ""
    run["user_feedback"] = (existing + "\n" + text).strip()
    save_state(project_root, task_id, state)
    sync_tasks_md(project_root, task_id)
    print(f"[OK] feedback added to {task_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# commit + push（从 task_done.py 迁移）
# ═══════════════════════════════════════════════════════════════════════════════

def _read_output_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _trim_imp_for_earlier_round(content):
    """去掉非最终轮的实现细节，只保留反馈部分。"""
    m = re.search(r'(?:## 实现思路|## 实现过程)', content)
    if m:
        content = content[:m.start()]
    return content.strip()


def _push_branch(branch):
    r = _run(f"git push origin {branch}")
    if r.returncode != 0:
        r = _run(f"git push --force-with-lease origin {branch}")
    if r.returncode != 0:
        r = _run(f"git push --force origin {branch}")
    return r.returncode == 0


def _do_commit_push(project_root, task_id, state):
    """组装 commit message，提交 + 推送。"""
    desc = state.get("desc", task_id)
    runs = state.get("runs", [])
    if not runs:
        return

    last_run = runs[-1]
    start_round = last_run.get("start_round", 1)
    outputs = last_run.get("outputs") or {}
    task_dir = os.path.join(_tasks_dir(project_root), task_id)

    imp_by_round = {}
    for basename in outputs.get("imp", []):
        m = re.search(r'-r(\d+)\.md$', basename)
        if m:
            imp_by_round[int(m.group(1))] = os.path.join(task_dir, basename)

    vfy_by_round = {}
    for basename in outputs.get("vfy", []):
        m = re.search(r'-r(\d+)\.md$', basename)
        if m:
            vfy_by_round[int(m.group(1))] = os.path.join(task_dir, basename)

    all_rounds = sorted(set(list(imp_by_round.keys()) + list(vfy_by_round.keys())))
    my_rounds = all_rounds  # outputs 已经被 cmd_run_done 过滤过
    if not my_rounds:
        return

    final_round = my_rounds[-1]
    whoami = state.get("assignee", "")

    commit_msg = f"[{task_id}] {desc}\n\n"

    imp_count = vfy_count = 0
    for r in my_rounds:
        commit_msg += f"## Round {r}\n\n"

        if r in imp_by_round:
            imp_count += 1
            content = _read_output_file(imp_by_round[r])
            if content:
                if r < final_round:
                    trimmed = _trim_imp_for_earlier_round(content)
                    if trimmed:
                        commit_msg += "### IMP\n\n" + trimmed
                else:
                    commit_msg += "### IMP\n\n" + content + "\n\n"

        if r in vfy_by_round:
            vfy_count += 1
            content = _read_output_file(vfy_by_round[r])
            if content:
                commit_msg += "### VFY\n\n" + content + "\n\n"

    commit_msg += f"---\nIMP{imp_count} VFY{vfy_count}"

    # git add（排除 tasks.md 和 .loop-engineering/）
    r = _run("git status --porcelain")
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        st = line[:2]
        fname = line[3:].strip()
        if st.strip() in ("M", "A", "??") and fname != "tasks.md" and not fname.startswith(".loop-engineering/"):
            _run(f'git add "{fname}"')

    # commit
    r = _run("git diff --cached --stat")
    if r.stdout.strip():
        r = _run(f'git commit -F -', input_text=commit_msg)
        if r.returncode == 0:
            print("  [OK] committed")

    # push
    branch = None
    r = _run("git branch --show-current")
    if r.returncode == 0 and r.stdout.strip():
        branch = r.stdout.strip()
    if not branch:
        r = _run(f"git branch --list 'agent/{whoami}/{task_id}-*'")
        branches = [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n') if l.strip()]
        branch = branches[0] if branches else None

    if branch:
        if _push_branch(branch):
            print(f"  [OK] pushed {branch}")

    # diff
    diff_path = os.path.join(project_root, f"agent-{whoami}-{task_id}.diff")
    r = _run(f"git diff master...{branch}")
    with open(diff_path, 'w', encoding='utf-8') as df:
        df.write(r.stdout.strip())
    print(f"Diff: {diff_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="统一任务状态管理")
    sub = parser.add_subparsers(dest="command")

    # init
    p = sub.add_parser("init")
    p.add_argument("--desc", required=True)
    p.add_argument("--assignee", required=True)
    p.add_argument("--project-root", default=None)

    # pick
    p = sub.add_parser("pick")
    p.add_argument("whoami")
    p.add_argument("--project-root", default=None)

    # status
    p = sub.add_parser("status")
    p.add_argument("task_id")
    p.add_argument("status", choices=["~", "x", "r", " "])
    p.add_argument("--project-root", default=None)

    # phase
    p = sub.add_parser("phase")
    p.add_argument("task_id")
    p.add_argument("phase_str", nargs="?", default="")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--project-root", default=None)

    # run-start
    p = sub.add_parser("run-start")
    p.add_argument("task_id")
    p.add_argument("--project-root", default=None)

    # run-done
    p = sub.add_parser("run-done")
    p.add_argument("task_id")
    p.add_argument("--result", required=True, choices=["pass", "fail"])
    p.add_argument("--do-commit", action="store_true")
    p.add_argument("--project-root", default=None)

    # get-phase
    p = sub.add_parser("get-phase")
    p.add_argument("--project-root", default=None)

    # feedback
    p = sub.add_parser("feedback")
    p.add_argument("task_id")
    p.add_argument("text")
    p.add_argument("--project-root", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    pr = args.project_root or _find_project_root()

    if args.command == "init":
        cmd_init(pr, args.desc, args.assignee)
    elif args.command == "pick":
        cmd_pick(pr, args.whoami)
    elif args.command == "status":
        cmd_status(pr, args.task_id, args.status)
    elif args.command == "phase":
        cmd_phase(pr, args.task_id, args.phase_str or None, args.clear)
    elif args.command == "run-start":
        cmd_run_start(pr, args.task_id)
    elif args.command == "run-done":
        cmd_run_done(pr, args.task_id, args.result, args.do_commit)
    elif args.command == "get-phase":
        cmd_get_phase(pr)
    elif args.command == "feedback":
        cmd_feedback(pr, args.task_id, args.text)


if __name__ == "__main__":
    main()
