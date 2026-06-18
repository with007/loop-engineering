#!/usr/bin/env python3
"""
从 tasks.md 选取下一个待办任务。
用法: python -m loop_engineering.scripts.task_pick <username>
输出: taskID=<id> desc=<描述> openSpec=<true|false>  或  NONE

从当前目录向上查找 loop-config.yaml 定位项目根目录。
"""
import subprocess, sys, re, os, hashlib


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def _find_project_root():
    """从 cwd 向上查找 loop-config.yaml，定位项目根目录."""
    p = os.getcwd()
    for _ in range(10):
        if os.path.exists(os.path.join(p, "loop-config.yaml")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.getcwd()  # fallback


def slugify(desc):
    """从描述生成 task_id."""
    desc = re.split(r'\s+—\s+', desc.strip())[0].strip().replace(' ', '-').lower()
    result = re.sub(r'[^a-z0-9-]', '', desc)
    result = re.sub(r'^-+|-+$', '', result)
    if len(result) < 3:
        result = 'task-' + hashlib.md5(desc.encode('utf-8')).hexdigest()[:8]
    return result[:40]


def main():
    if len(sys.argv) < 2:
        print("Usage: task_pick.py <username>")
        sys.exit(1)

    whoami = sys.argv[1]
    project_root = _find_project_root()
    tasks_path = os.path.join(project_root, "tasks.md")

    try:
        with open(tasks_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print("NONE")
        return

    for line in content.split('\n'):
        match = re.match(r'^- \[ \]\s+(.+?)\s+\(→\s*' + re.escape(whoami) + r'\)', line)
        if not match:
            continue

        desc = match.group(1).strip()
        task_id = slugify(desc)

        result = run(f"git ls-remote --heads origin agent/{whoami}/{task_id}")
        if result.stdout.strip():
            continue

        open_spec = "true" if os.path.isdir(os.path.join(project_root, f"openspec/changes/{task_id}")) else "false"

        print(f"taskID={task_id} desc={desc} openSpec={open_spec}")
        return

    print("NONE")


if __name__ == "__main__":
    main()
