#!/usr/bin/env python3
"""
任务完成收尾。生成 diff、更新 tasks.md ([~]→[x])、弹通知。
注意：不 commit、不 push、不 checkout —— 由调用方（SKILL.md Step 5）负责。
用法: python -m loop_engineering.scripts.task_done <username> <taskID> [IMP序号] [VFY轮数]
"""
import subprocess, sys, re, time, os, hashlib
from datetime import datetime


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def _find_project_root():
    p = os.getcwd()
    for _ in range(10):
        if os.path.exists(os.path.join(p, "loop-config.yaml")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.getcwd()


def slugify(desc):
    desc = re.split(r'\s+—\s+', desc.strip())[0].strip().replace(' ', '-').lower()
    result = re.sub(r'[^a-z0-9-]', '', desc)
    result = re.sub(r'^-+|-+$', '', result)
    if len(result) < 3:
        result = 'task-' + hashlib.md5(desc.encode('utf-8')).hexdigest()[:8]
    return result[:40]


def update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root):
    """更新 tasks.md: [ ]/[~] → [x] 并追加运行记录"""
    now = datetime.now().strftime("%H:%M")
    record = f" — {now} IMP{imp_n} VFY{vfy_n} PASS"
    updated = False
    tasks_path = os.path.join(project_root, "tasks.md")
    try:
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open(tasks_path, "w", encoding="utf-8") as f:
            for line in lines:
                m = re.match(r'^(- \[[ ~]\]\s+)(.+?)(\s+\(→\s*' + re.escape(whoami) + r'\).*)$', line)
                if m and slugify(m.group(2)) == task_id:
                    f.write(f"- [x] {m.group(2)}{m.group(3)}{record}\n")
                    updated = True
                else:
                    f.write(line)

        status = "[x]" if updated else "未匹配"
        print(f"tasks.md: {task_id} → {status}")
    except Exception as e:
        print(f"Warning: tasks.md update failed: {e}")


def main():
    if len(sys.argv) < 3:
        print("Usage: task_done.py <username> <taskID> [IMP序号] [VFY轮数]")
        sys.exit(1)

    whoami = sys.argv[1]
    task_id = sys.argv[2]
    imp_n = sys.argv[3] if len(sys.argv) > 3 else "1"
    vfy_n = sys.argv[4] if len(sys.argv) > 4 else "1"
    branch = f"agent/{whoami}/{task_id}"
    diff_file = f"agent-{whoami}-{task_id}.diff"

    project_root = _find_project_root()

    print(f"=== 任务完成: {task_id} ===")

    # 生成 diff（用 origin/ 远程引用，避免本地分支状态异常导致空 diff）
    run(f"git diff -U10 origin/master...origin/{branch} > {diff_file}")
    print(f"Diff: {diff_file}")

    # 更新 tasks.md
    update_tasks_md(task_id, whoami, imp_n, vfy_n, project_root)

    # 弹通知（不用 shell=True，避免 cmd.exe 破坏含换行符的参数）
    notify_path = os.path.join(project_root, ".claude", "scripts", "notify.py")
    subprocess.Popen(
        [sys.executable, notify_path, f"{branch} 合入",
         f"编译/测试/审计通过\n点 OK 打开 {diff_file}", diff_file]
    )
    time.sleep(2)

    print(f"=== {task_id} 已推送，等人合入 ===")


if __name__ == "__main__":
    main()
