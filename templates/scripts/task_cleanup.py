#!/usr/bin/env python3
"""清理已合入的 agent 分支（独立部署版）。

零包依赖，纯 stdlib + git 命令。由 loop setup 部署到 .claude/scripts/。
用法: python .claude/scripts/task_cleanup.py <username> [--format shell] [--project-root <dir>]
"""
import subprocess, sys, os, shlex, re


def _run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=cwd, timeout=15)


def _has_remote(cwd=None):
    try:
        r = _run("git remote", cwd=cwd)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _detect_default_branch(cwd=None):
    for ref in ["master", "main", "origin/master", "origin/main"]:
        try:
            r = _run(f"git rev-parse --verify {ref}", cwd=cwd)
            if r.returncode == 0:
                return ref
        except Exception:
            continue
    return "master"


def is_merged(branch, base=None, is_remote=True, repo_path=None):
    """判断分支是否已合入默认分支.

    Args:
        branch: 分支名（远程如 'origin/agent/with/task-xxx'，本地如 'agent/with/task-xxx'）
        base: 默认分支名，默认自动检测 master/main
        is_remote: True 表示远程分支（有 origin/ 前缀），False 表示本地分支
        repo_path: git 仓库路径

    Returns:
        bool — True 表示已合入
    """
    if base is None:
        base = _detect_default_branch(cwd=repo_path)

    has_remote = _has_remote(cwd=repo_path)

    if is_remote and has_remote:
        short = branch.replace('origin/', '')

        # 1. 本地祖先检测（用户 merge 后立刻生效）
        r = _run(f"git merge-base --is-ancestor {short} {base}", cwd=repo_path)
        if r.returncode == 0:
            return True

        # 2. 本地已合并列表
        r = _run(f"git branch --merged {base}", cwd=repo_path)
        if short in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True

        # 3. 远程已合并列表
        r = _run(f"git branch -r --merged origin/{base}", cwd=repo_path)
        if branch in [l.strip() for l in r.stdout.strip().split('\n')]:
            return True

        # 4. 远程祖先检测（squash/rebase 兜底）
        r = _run(f"git merge-base --is-ancestor origin/{short} origin/{base}", cwd=repo_path)
        if r.returncode == 0:
            return True

    else:
        b = branch.replace('origin/', '') if is_remote else branch

        # 1. 祖先检测
        r = _run(f"git merge-base --is-ancestor {b} {base}", cwd=repo_path)
        if r.returncode == 0:
            return True

        # 2. 已合并列表
        r = _run(f"git branch --merged {base}", cwd=repo_path)
        if b in [l.strip().replace('* ', '') for l in r.stdout.strip().split('\n')]:
            return True

    return False


def _extract_task_id_from_branch(branch_name):
    """从分支名提取 task_id."""
    basename = branch_name.split('/')[-1].strip()
    if re.match(r'^[a-f0-9]{8}$', basename):
        return basename
    parts = basename.split('-', 1)
    return parts[0] if parts[0] else None


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 2:
        print("Usage: task_cleanup.py <username> [--format shell] [--project-root <dir>]")
        sys.exit(1)

    whoami = sys.argv[1]
    fmt = None
    project_root = None
    for i, arg in enumerate(sys.argv):
        if arg == "--format" and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]
        elif arg == "--project-root" and i + 1 < len(sys.argv):
            project_root = sys.argv[i + 1]

    if not project_root:
        project_root = os.getcwd()

    prefix = f"agent/{whoami}/"

    print(f"=== 检查已合入的 {prefix} 分支 ===")

    # fetch
    _run("git fetch origin --prune 2>/dev/null || true", cwd=project_root)

    # 远程分支
    result = _run("git branch -r", cwd=project_root)
    remote_lines = result.stdout.strip().split('\n')
    remote_candidates = [l.strip() for l in remote_lines if prefix in l]

    # 本地分支
    result = _run("git branch", cwd=project_root)
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
        task_id = _extract_task_id_from_branch(short_name) or short_name.replace(prefix, '')
        print(f"清理: {short_name}")

        if info['remote']:
            r = _run(f"git push origin --delete {short_name}", cwd=project_root)
            if r.returncode != 0:
                print(f"  (远程删除失败: {r.stderr.strip()})")
        else:
            print(f"  (仅本地分支)")

        r = _run(f"git branch -D {short_name}", cwd=project_root)
        if r.returncode != 0:
            print(f"  (本地已不存在)")

        diff_file = os.path.join(project_root, f"agent-{whoami}-{task_id}.diff")
        if os.path.exists(diff_file):
            os.remove(diff_file)
            print(f"  已删除 {diff_file}")

        cleaned_ids.append(task_id)

    print("=== 完成 ===")

    if fmt == "shell":
        print("STATUS=ok")
        count = len(cleaned_ids)
        print(f"CLEANED={count}")
        ids_str = ",".join(cleaned_ids)
        print(f"BRANCH_IDS={shlex.quote(ids_str)}")


if __name__ == "__main__":
    main()
