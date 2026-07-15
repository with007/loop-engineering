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
import subprocess
import sys
import time
from datetime import datetime, timezone

# ── Import task_line (handles both src/ and .claude/scripts/ locations) ──
try:
    from task_line import TaskLine, load_tasks, save_tasks, replace_task, find_project_root as _find_root
except ImportError:
    _d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        _scripts = os.path.join(_d, '.claude', 'scripts')
        if os.path.isdir(_scripts):
            sys.path.insert(0, _scripts)
            break
        _d = os.path.dirname(_d)
    from task_line import TaskLine, load_tasks, save_tasks, replace_task, find_project_root as _find_root


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
# state.json 读写
# ═══════════════════════════════════════════════════════════════════════════════

def _tasks_dir(project_root):
    return os.path.join(project_root, ".loop-engineering", "tasks")


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
                "created_at": _now_iso(),
                "phase": None,
                "runs": [],
            }
            # 恢复 feedback（如果有缩进行）
            if tl.feedback:
                state["runs"].append({
                    "started_at": None,
                    "completed_at": _now_iso(),
                    "result": "pass" if tl.status == "x" else None,
                    "start_round": 1,
                    "end_round": 1,
                    "user_feedback": "\n".join(tl.feedback),
                    "outputs": None,
                })
            save_state(project_root, task_id, state)
            return state
    return None


def find_active_phase(project_root):
    """遍历所有 state.json，返回 (task_id, phase_str) 或 (None, None)。"""
    tasks_dir = _tasks_dir(project_root)
    if not os.path.isdir(tasks_dir):
        return None, None
    for tid in os.listdir(tasks_dir):
        state = load_state(project_root, tid)
        if state and state.get("phase"):
            return tid, state["phase"]
    return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# tasks.md 块级同步
# ═══════════════════════════════════════════════════════════════════════════════

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

    # 反馈行：取最近一次 run 的 user_feedback
    runs = state.get("runs", [])
    active_run = next((r for r in runs if r.get("completed_at") is None), None)
    source = active_run or (runs[-1] if runs else None)
    if source and source.get("user_feedback"):
        for line in source["user_feedback"].split("\n"):
            tl.feedback.append(line.strip())

    # 替换或追加
    replace_task(entries, task_id, tl)
    save_tasks(tasks_path, entries)


def init_state_from_all_md(project_root):
    """遍历 tasks.md，为所有缺 state.json 的任务创建最小 state.json。"""
    tasks_path = os.path.join(project_root, "tasks.md")
    if not os.path.exists(tasks_path):
        return
    entries = load_tasks(tasks_path)
    for tl, _ in entries:
        if tl and tl.task_id and not os.path.exists(_state_path(project_root, tl.task_id)):
            state = {
                "task_id": tl.task_id,
                "desc": tl.description,
                "assignee": tl.assignee,
                "created_at": _now_iso(),
                "status": tl.status,
                "phase": None,
                "runs": [],
            }
            save_state(project_root, tl.task_id, state)


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
    init_state_from_all_md(project_root)
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
                    print(f"WARNING: [r] task {task_id} — branch not found (local/reflog), skipping.",
                          file=sys.stderr)
                    continue
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

    # 计算 start_round
    runs = state.get("runs", [])
    if runs:
        last_end = runs[-1].get("end_round", 0) or 0
        start_round = last_end + 1
    else:
        start_round = 1

    # 取最新 user_feedback
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

    # 扫描输出文件
    task_dir = os.path.join(_tasks_dir(project_root), task_id)
    imp_files = sorted(glob.glob(os.path.join(task_dir, "imp-output-r*.md")))
    vfy_files = sorted(glob.glob(os.path.join(task_dir, "vfy-output-r*.md")))
    run["outputs"] = {
        "imp": [os.path.basename(f) for f in imp_files],
        "vfy": [os.path.basename(f) for f in vfy_files],
    }
    run["end_round"] = run["start_round"] + max(len(imp_files), len(vfy_files)) - 1

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
    task_dir = os.path.join(_tasks_dir(project_root), task_id)

    # 收集输出文件（只收集 >= start_round 的）
    imp_files = sorted(glob.glob(os.path.join(task_dir, "imp-output-r*.md")))
    vfy_files = sorted(glob.glob(os.path.join(task_dir, "vfy-output-r*.md")))

    imp_by_round = {}
    for f in imp_files:
        m = re.search(r'-r(\d+)\.md$', os.path.basename(f))
        if m:
            imp_by_round[int(m.group(1))] = f

    vfy_by_round = {}
    for f in vfy_files:
        m = re.search(r'-r(\d+)\.md$', os.path.basename(f))
        if m:
            vfy_by_round[int(m.group(1))] = f

    all_rounds = sorted(set(list(imp_by_round.keys()) + list(vfy_by_round.keys())))
    my_rounds = [r for r in all_rounds if r >= start_round]
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
