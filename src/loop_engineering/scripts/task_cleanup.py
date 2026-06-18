#!/usr/bin/env python3
"""
清理已合入的 agent 分支。
用法: python -m loop_engineering.scripts.task_cleanup <username>
"""
import subprocess, sys, os


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


def is_merged(branch):
    """判断远程分支是否已合入 master"""
    r = run(f"git branch -r --merged origin/master")
    if branch in [l.strip() for l in r.stdout.strip().split('\n')]:
        return True
    short = branch.replace('origin/', '')
    r = run(f"git branch --merged master")
    if short in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
        return True
    r = run(f"git merge-base --is-ancestor origin/{branch} origin/master")
    if r.returncode == 0:
        return True
    r = run(f"git merge-base --is-ancestor origin/{branch} master")
    if r.returncode == 0:
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: task_cleanup.py <username>")
        sys.exit(1)

    whoami = sys.argv[1]
    prefix = f"agent/{whoami}/"
    project_root = _find_project_root()

    print(f"=== 检查已合入的 {prefix} 分支 ===")

    run("git fetch origin --prune")

    result = run(f"git branch -r")
    lines = result.stdout.strip().split('\n')
    candidates = [l.strip().replace('origin/', '') for l in lines if prefix in l]

    if not candidates:
        print("无 agent 分支")
        return

    merged = [b for b in candidates if is_merged(b)]

    if not merged:
        print("无已合入分支")
        return

    for branch in merged:
        print(f"清理: {branch}")
        r = run(f"git push origin --delete {branch}")
        if r.returncode != 0:
            print(f"  (远程删除失败: {r.stderr.strip()})")
        r = run(f"git branch -D {branch}")
        if r.returncode != 0:
            print(f"  (本地已不存在)")
        task_id = branch.replace(prefix, '')
        diff_file = os.path.join(project_root, f"agent-{whoami}-{task_id}.diff")
        if os.path.exists(diff_file):
            os.remove(diff_file)
            print(f"  已删除 {diff_file}")

    print("=== 完成 ===")


if __name__ == "__main__":
    main()
