#!/usr/bin/env python3
"""
清理已合入的 agent 分支。
用法: python -m loop_engineering.scripts.task_cleanup <username>
"""
import subprocess, sys, os, shlex
from loop_engineering.task_id import extract_task_id_from_branch
from loop_engineering.path_utils import find_project_root
from loop_engineering.git_utils import is_merged


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_cleanup.py <username> [--format shell]")
        sys.exit(1)

    whoami = sys.argv[1]
    fmt = None
    for i, arg in enumerate(sys.argv):
        if arg == "--format" and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]

    prefix = f"agent/{whoami}/"
    project_root = find_project_root()

    print(f"=== 检查已合入的 {prefix} 分支 ===")

    # ... (same branch scanning logic)
    run("git fetch origin --prune 2>/dev/null || true")
    result = run(f"git branch -r")
    remote_lines = result.stdout.strip().split('\n')
    remote_candidates = [l.strip() for l in remote_lines if prefix in l]
    remote_names = set(c.replace('origin/', '') for c in remote_candidates)

    result = run(f"git branch")
    local_lines = result.stdout.strip().split('\n')
    local_candidates = [l.strip().replace('* ', '') for l in local_lines if prefix in l]

    all_branches = {}
    for c in remote_candidates:
        short = c.replace('origin/', '')
        all_branches[short] = {'remote': c, 'local': short in local_candidates}
    for c in local_candidates:
        if c not in all_branches:
            all_branches[c] = {'remote': None, 'local': True}

    if not all_branches:
        print("无 agent 分支")
        if fmt == "shell":
            print("STATUS=none")
            print("CLEANED=0")
        return

    merged = []
    for short_name, info in all_branches.items():
        if info['remote']:
            if is_merged(info['remote'], is_remote=True, repo_path=project_root):
                merged.append((short_name, info))
        elif is_merged(short_name, is_remote=False, repo_path=project_root):
            merged.append((short_name, info))

    if not merged:
        print("无已合入分支")
        if fmt == "shell":
            print("STATUS=ok")
            print("CLEANED=0")
            print("BRANCHES=")
        return

    cleaned_ids = []
    for short_name, info in merged:
        task_id = extract_task_id_from_branch(short_name) or short_name.replace(prefix, '')
        print(f"清理: {short_name}")

        if info['remote']:
            r = run(f"git push origin --delete {short_name}")
            if r.returncode != 0:
                print(f"  (远程删除失败: {r.stderr.strip()})")
        else:
            print(f"  (仅本地分支)")

        r = run(f"git branch -D {short_name}")
        if r.returncode != 0:
            print(f"  (本地已不存在)")

        diff_file = os.path.join(project_root, f"agent-{whoami}-{task_id}.diff")
        if os.path.exists(diff_file):
            os.remove(diff_file)
            print(f"  已删除 {diff_file}")

        cleaned_ids.append(task_id)

    print("=== 完成 ===")

    if fmt == "shell":
        print(f"STATUS=ok")
        count = len(cleaned_ids)
        print(f"CLEANED={count}")
        ids_str = ",".join(cleaned_ids)
        print(f"BRANCH_IDS={shlex.quote(ids_str)}")


if __name__ == "__main__":
    main()
