#!/usr/bin/env python3
"""
任务完成收尾。生成 diff、更新 tasks.md ([~]→[x])、弹通知。
注意：不 commit、不 push、不 checkout —— 由调用方（SKILL.md Step 5）负责。
用法: python -m loop_engineering.scripts.task_done <username> <taskID> [IMP序号] [VFY轮数]
"""
import subprocess, sys, re, time, os, json
from datetime import datetime, timezone
from loop_engineering.task_id import make_branch_name, parse_task_id
from loop_engineering.config import is_project_dir


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def _find_project_root():
    p = os.getcwd()
    for _ in range(10):
        if is_project_dir(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.getcwd()


def _default_branch():
    """获取默认分支引用。优先级: local master > local main > origin/master > origin/main."""
    for ref in ["master", "main", "origin/master", "origin/main"]:
        if run(f"git rev-parse --verify {ref}").returncode == 0:
            return ref
    return "master"


def update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root):
    """更新 tasks.md: [ ]/[~]/[r] → [x] 并追加运行记录.

    [r] 任务在旧记录后追加新记录，用 · 分隔。
    """
    now = datetime.now().strftime("%H:%M")
    record = f" — {now} IMP{imp_n} VFY{vfy_n} PASS"
    updated = False
    tasks_path = os.path.join(project_root, "tasks.md")
    try:
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(tasks_path, "w", encoding="utf-8") as f:
            for line in lines:
                m = re.match(r'^(- \[[ r~]\]\s+)(.+?)(\s+\(→\s*' + re.escape(whoami) + r'\).*)$', line)
                if m and parse_task_id(line) == task_id:
                    if line.startswith('- [r] '):
                        # reopen 任务：追加新记录
                        new_meta = m.group(3).rstrip() + " · " + now + f" IMP{imp_n} VFY{vfy_n} PASS"
                        f.write(f"- [x] {m.group(2)}{new_meta}\n")
                    else:
                        f.write(f"- [x] {m.group(2)}{m.group(3)}{record}\n")
                    updated = True
                else:
                    f.write(line)

        status = "[x]" if updated else "未匹配"
        print(f"tasks.md: {task_id} → {status}")
    except Exception as e:
        print(f"Warning: tasks.md update failed: {e}")


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 3:
        print("Usage: task_done.py <username> <taskID> [IMP序号] [VFY轮数]")
        sys.exit(1)

    whoami = sys.argv[1]
    task_id = sys.argv[2]
    imp_n = sys.argv[3] if len(sys.argv) > 3 else "1"
    vfy_n = sys.argv[4] if len(sys.argv) > 4 else "1"
    # 查找实际分支名（agent/whoami/task_id-*）
    r = run(f'git branch --list "agent/{whoami}/{task_id}-*"')
    branches = [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n') if l.strip()]
    branch = branches[0] if branches else f"agent/{whoami}/{task_id}"
    diff_file = f"agent-{whoami}-{task_id}.diff"

    project_root = None
    for i, arg in enumerate(sys.argv):
        if arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]
            break
    if not project_root:
        project_root = _find_project_root()

    print(f"=== 任务完成: {task_id} ===")

    # 生成 diff（写到主 worktree，方便人审查和 cleanup 清理）
    base = _default_branch()
    diff_path = os.path.join(project_root, diff_file)
    run(f"git diff -U10 {base}...{branch} > {diff_path}")
    print(f"Diff: {diff_path}")

    # 更新 tasks.md
    update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root)

    # 写 run log（结构化日志）
    _write_run_log(project_root, task_id, whoami, imp_n, vfy_n, branch)

    # 弹通知
    notify_path = os.path.join(project_root, ".claude", "scripts", "notify.py")
    subprocess.Popen(
        [sys.executable, notify_path, f"{branch} 合入",
         f"编译/测试/审计通过\n点 OK 打开 {diff_path}", diff_path]
    )
    time.sleep(2)

    print(f"=== {task_id} 已推送，等人合入 ===")


def _write_run_log(project_root, task_id, whoami, imp_n, vfy_n, branch):
    """写结构化 run log."""
    from loop_engineering.runlog import write_run_log
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

    entry = {
        "task_id": task_id,
        "task_desc": task_desc[:200],
        "branch": branch,
        "whoami": whoami,
        "phase": "verify",
        "imp_round": int(imp_n),
        "vfy_round": int(vfy_n),
        "result": "PASS",
    }
    write_run_log(project_root, entry)


if __name__ == "__main__":
    main()
