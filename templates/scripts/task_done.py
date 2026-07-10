#!/usr/bin/env python3
"""任务完成收尾（独立部署版）。

零包依赖，纯 stdlib + git 命令 + 内置 TaskLine 解析器。
由 loop setup 部署到 .claude/scripts/。
用法: python .claude/scripts/task_done.py <username> <taskID> [IMP序号] [VFY轮数] [--project-root <dir>] [--task-desc <desc>] [--do-commit] [--format shell]

--do-commit: 读取 imp-output.md + vfy-output.md 组装 commit message，git add/commit/push
--task-desc: 任务描述（用于 commit message 标题）
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime


# ── TaskLine 解析器 ──

_TASK_LINE_RE = re.compile(
    r'^- \[(.)\]\s+'             # checkbox: - [x]
    r'(.+?)'                      # description (non-greedy)
    r'(?:\s+\(→\s*(\w+)\))?'     # optional assignee: (→ whoami)
    r'(?:\s+\[([a-f0-9]{8})\])?' # optional task_id: [xxxxxxxx]
    r'(?:\s+—\s+(.+))?'          # optional meta: — text
    r'$'
)


class TaskLine:
    """tasks.md 中单行任务的解析和格式化（零依赖版）."""

    __slots__ = ("status", "description", "assignee", "task_id", "meta", "feedback")

    def __init__(self, status=" ", description="", assignee="", task_id="", meta="", feedback=None):
        self.status = status
        self.description = description
        self.assignee = assignee
        self.task_id = task_id
        self.meta = meta
        self.feedback = feedback if feedback is not None else []

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


# ── 工具函数 ──

def _run(cmd, input_text=None):
    kwargs = {"shell": True, "capture_output": True, "text": True,
              "encoding": "utf-8", "errors": "replace"}
    if input_text is not None:
        kwargs["input"] = input_text
    return subprocess.run(cmd, **kwargs)


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


def _get_default_branch(repo_path=None):
    """获取默认分支引用."""
    for ref in ["master", "main", "origin/master", "origin/main"]:
        try:
            r = _run(f"git rev-parse --verify {ref}")
            if r.returncode == 0:
                return ref
        except Exception:
            continue
    return "master"


def _write_run_log(project_root, task_id, whoami, imp_n, vfy_n, branch):
    """写结构化 run log."""
    runs_dir = os.path.join(project_root, ".loop-engineering", "runs")
    os.makedirs(runs_dir, exist_ok=True)

    # 读取任务描述
    tasks_path = os.path.join(project_root, "tasks.md")
    task_desc = ""
    try:
        with open(tasks_path, "r", encoding="utf-8") as f:
            for line in f:
                if task_id in line.lower().replace(" ", "-"):
                    task_desc = line.strip().lstrip("- [x~ ]").strip()
                    break
    except Exception:
        pass

    now = datetime.now().isoformat()
    entry = {
        "task_id": task_id,
        "task_desc": task_desc[:200],
        "branch": branch,
        "whoami": whoami,
        "phase": "verify",
        "imp_round": int(imp_n),
        "vfy_round": int(vfy_n),
        "result": "PASS",
        "version": 1,
        "started": now,
        "completed": now,
        "summary": "",
        "files_changed": [],
        "tests": [],
        "fail_reason": None,
        "open_spec": False,
        "hint": None,
    }

    fname = f"{task_id}--IMP{imp_n}--VFY{vfy_n}.json"
    fpath = os.path.join(runs_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False, default=str)


def _read_output_file(path):
    """读取 implementer/verifier 输出文件."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


# ── 主逻辑 ──

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 3:
        print("Usage: task_done.py <username> <taskID> [IMP序号] [VFY轮数] [--project-root <dir>] [--format shell]")
        sys.exit(1)

    whoami = sys.argv[1]
    task_id = sys.argv[2]
    imp_n = sys.argv[3] if len(sys.argv) > 3 else "1"
    vfy_n = sys.argv[4] if len(sys.argv) > 4 else "1"

    # 过滤掉位置参数中可能误传入的非数字
    if not imp_n.isdigit():
        imp_n = "1"
    if not vfy_n.isdigit():
        vfy_n = "1"

    # 查找实际分支名
    r = _run(f'git branch --list "agent/{whoami}/{task_id}-*"')
    branches = [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n') if l.strip()]
    branch = branches[0] if branches else f"agent/{whoami}/{task_id}"
    diff_file = f"agent-{whoami}-{task_id}.diff"

    project_root = None
    fmt = None
    task_desc = ""
    do_commit = False
    for i, arg in enumerate(sys.argv):
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
        elif arg == "--task-desc" and i + 1 < len(sys.argv):
            task_desc = sys.argv[i + 1]
        elif arg == "--do-commit":
            do_commit = True
        elif arg == "--format" and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]
    if not project_root:
        project_root = _find_project_root()

    print(f"=== 任务完成: {task_id} ===")

    # ── commit + push ──
    if do_commit:
        commit_title = task_desc or task_id
        imp_output = _read_output_file(os.path.join(project_root, ".loop-engineering", "imp-output.md"))
        vfy_output = _read_output_file(os.path.join(project_root, ".loop-engineering", "vfy-output.md"))

        commit_msg = f"[{task_id}] {commit_title}\n\n"
        if imp_output:
            commit_msg += imp_output + "\n"
        if vfy_output:
            commit_msg += vfy_output + "\n"
        commit_msg += f"---\nIMP{imp_n} VFY{vfy_n}"

        # git add 改动文件（排除 tasks.md，只提交代码变更）
        r = _run("git status --porcelain")
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            status = line[:2]
            fname = line[3:].strip()
            if status.strip() in ("M", "A", "??") and fname != "tasks.md" and not fname.startswith(".loop-engineering/"):
                _run(f'git add "{fname}"')

        # 检查是否有东西可 commit
        r = _run("git diff --cached --stat")
        if r.stdout.strip():
            _run(f'git commit -F -', input_text=commit_msg)
            print("  [OK] committed")
            r = _run(f"git push origin {branch}")
            if r.returncode != 0:
                print(f"  [WARN] push failed: {r.stderr.strip()[:120]}")
            else:
                print(f"  [OK] pushed {branch}")
        else:
            print("  (无改动，跳过 commit)")

    # 生成 diff
    base = _get_default_branch(project_root)
    diff_path = os.path.join(project_root, diff_file)
    _run(f"git diff -U10 {base}...{branch} > {diff_path}")
    print(f"Diff: {diff_path}")

    # 更新 tasks.md
    _update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root)

    # 写 run log
    _write_run_log(project_root, task_id, whoami, imp_n, vfy_n, branch)

    # 弹通知
    notify_path = os.path.join(project_root, ".claude", "scripts", "notify.py")
    subprocess.Popen(
        [sys.executable, notify_path, f"{branch} 合入",
         f"编译/测试/审计通过\n点 OK 打开 {diff_path}", diff_path]
    )
    time.sleep(2)

    print(f"=== {task_id} 已推送，等人合入 ===")

    if fmt == "shell":
        print(f"STATUS=ok")
        print(f"TASK_ID={shlex.quote(task_id)}")
        print(f"BRANCH={shlex.quote(branch)}")
        print(f"DIFF={shlex.quote(diff_path)}")


def _update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root):
    """更新 tasks.md: [ ]/[~]/[r] → [x] 并追加运行记录."""
    now = datetime.now().strftime("%H:%M")
    updated = False
    tasks_path = os.path.join(project_root, "tasks.md")
    try:
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(tasks_path, "w", encoding="utf-8") as f:
            for line in lines:
                tl = TaskLine.parse(line.rstrip('\n'))
                if tl and tl.task_id == task_id and tl.assignee == whoami and tl.status in (" ", "~", "r"):
                    if tl.status == "r":
                        old_meta = tl.meta
                        new_meta = (old_meta + " · " + now + f" IMP{imp_n} VFY{vfy_n} PASS") if old_meta else (now + f" IMP{imp_n} VFY{vfy_n} PASS")
                        tl.status = "x"
                        tl.meta = new_meta
                    else:
                        tl.status = "x"
                        tl.meta = (tl.meta + " · " + now + f" IMP{imp_n} VFY{vfy_n} PASS") if tl.meta else (now + f" IMP{imp_n} VFY{vfy_n} PASS")
                    f.write(tl.format() + "\n")
                    updated = True
                else:
                    f.write(line)

        status = "[x]" if updated else "未匹配"
        print(f"tasks.md: {task_id} → {status}")
    except Exception as e:
        print(f"Warning: tasks.md update failed: {e}")


if __name__ == "__main__":
    main()
