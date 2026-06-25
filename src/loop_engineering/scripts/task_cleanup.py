#!/usr/bin/env python3
"""
清理已合入的 agent 分支。
用法: python -m loop_engineering.scripts.task_cleanup <username>
"""
import subprocess, sys, os
from loop_engineering.task_id import extract_task_id_from_branch


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def _default_branch():
    """获取默认分支引用。优先级: local master > local main > origin/master > origin/main."""
    for ref in ["master", "main", "origin/master", "origin/main"]:
        if run(f"git rev-parse --verify {ref}").returncode == 0:
            return ref
    return "master"


def is_merged(branch, is_remote=True):
    """判断分支是否已合入默认主分支.

    Args:
        branch: 分支名（远程如 'origin/agent/with/task-xxx'，本地如 'agent/with/task-xxx'）
        is_remote: True 表示远程分支，False 表示本地分支
    """
    base = _default_branch()
    if is_remote:
        r = run(f"git branch -r --merged origin/{base}")
        if branch in [l.strip() for l in r.stdout.strip().split('\n')]:
            return True
        short = branch.replace('origin/', '')
        r = run(f"git branch --merged {base}")
        if short in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True
        r = run(f"git merge-base --is-ancestor origin/{branch} origin/{base}")
        if r.returncode == 0:
            return True
        r = run(f"git merge-base --is-ancestor origin/{branch} {base}")
        if r.returncode == 0:
            return True
    else:
        r = run(f"git branch --merged {base}")
        if branch in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True
        r = run(f"git merge-base --is-ancestor {branch} {base}")
        if r.returncode == 0:
            return True
    return False


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


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_cleanup.py <username>")
        sys.exit(1)

    whoami = sys.argv[1]
    prefix = f"agent/{whoami}/"
    project_root = _find_project_root()

    print(f"=== 检查已合入的 {prefix} 分支 ===")

    # 1. 远程分支（有 origin 时）
    run("git fetch origin --prune 2>/dev/null || true")
    result = run(f"git branch -r")
    remote_lines = result.stdout.strip().split('\n')
    remote_candidates = [l.strip() for l in remote_lines if prefix in l]
    # 去掉 origin/ 前缀得到短分支名
    remote_names = set(c.replace('origin/', '') for c in remote_candidates)

    # 2. 本地分支（无 origin 时也能清理）
    result = run(f"git branch")
    local_lines = result.stdout.strip().split('\n')
    local_candidates = [l.strip().replace('* ', '') for l in local_lines if prefix in l]

    # 合并去重
    all_branches = {}
    for c in remote_candidates:
        short = c.replace('origin/', '')
        all_branches[short] = {'remote': c, 'local': short in local_candidates}
    for c in local_candidates:
        if c not in all_branches:
            all_branches[c] = {'remote': None, 'local': True}

    if not all_branches:
        print("无 agent 分支")
        return

    # 判断每个分支是否已合入
    merged = []
    for short_name, info in all_branches.items():
        # 优先用远程分支检查，没有远程则用本地
        if info['remote']:
            if is_merged(info['remote'], is_remote=True):
                merged.append((short_name, info))
        elif is_merged(short_name, is_remote=False):
            merged.append((short_name, info))

    if not merged:
        print("无已合入分支")
        return

    for short_name, info in merged:
        task_id = extract_task_id_from_branch(short_name) or short_name.replace(prefix, '')
        print(f"清理: {short_name}")

        # 远程分支：先删远程再删本地
        if info['remote']:
            r = run(f"git push origin --delete {short_name}")
            if r.returncode != 0:
                print(f"  (远程删除失败: {r.stderr.strip()})")
        else:
            print(f"  (仅本地分支)")

        # 删本地分支
        r = run(f"git branch -D {short_name}")
        if r.returncode != 0:
            print(f"  (本地已不存在)")

        # 删 diff 文件
        diff_file = os.path.join(project_root, f"agent-{whoami}-{task_id}.diff")
        if os.path.exists(diff_file):
            os.remove(diff_file)
            print(f"  已删除 {diff_file}")

    print("=== 完成 ===")


if __name__ == "__main__":
    main()
