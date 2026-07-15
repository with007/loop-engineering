#!/usr/bin/env python3
"""任务完成收尾（独立部署版）。

零包依赖，纯 stdlib + git 命令。
由 loop setup 部署到 .claude/scripts/。
用法: python .claude/scripts/task_done.py <username> <taskID> [IMP序号] [VFY轮数] [--project-root <dir>] [--output-dir <dir>] [--task-desc <desc>] [--do-commit] [--format shell]

--project-root: 主工程根目录（tasks.md、diff、run_log 所在）
--output-dir:   imp-output-r*.md / vfy-output-r*.md 所在目录，默认当前目录
--do-commit:    收集所有轮次文件，交替拼装 commit message，git add/commit/push
--task-desc:    任务描述（用于 commit message 标题）
"""
import json
import glob
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime

from task_line import update_task, find_project_root


# ── 工具函数 ──

def _run(cmd, input_text=None):
    kwargs = {"shell": True, "capture_output": True, "text": True,
              "encoding": "utf-8", "errors": "replace"}
    if input_text is not None:
        kwargs["input"] = input_text
    return subprocess.run(cmd, **kwargs)



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


def _trim_imp_for_earlier_round(content):
    """精简非末轮 IMP 报告：只保留反馈和修复内容，去掉实现思路/过程/变更概要/兼容性."""
    if not content:
        return ""
    # 取到 ## 实现思路 之前的内容（即 用户反馈 + 验证反馈）
    for cutoff in ["\n## 实现思路", "\n## 实现过程"]:
        idx = content.find(cutoff)
        if idx > 0:
            content = content[:idx]
            break
    return content.strip() + "\n\n" if content.strip() else ""


def _collect_round_files(loop_dir, pattern):
    """收集轮次文件，返回 {round_num: filepath} 字典."""
    result = {}
    for fpath in glob.glob(os.path.join(loop_dir, pattern)):
        # 从文件名提取轮次号: imp-output-r{N}.md 或 vfy-output-r{N}.md
        basename = os.path.basename(fpath)
        try:
            # 提取 -r 后面的数字
            num_str = basename.split("-r")[-1].replace(".md", "")
            r = int(num_str)
            result[r] = fpath
        except (ValueError, IndexError):
            continue
    return result


# ── 主逻辑 ──

def _push_branch(branch):
    """推送分支到远程，分叉时自动 force-with-lease → force."""
    r = _run(f"git push origin {branch}")
    if r.returncode == 0:
        print(f"  [OK] pushed {branch}")
        return True

    stderr = r.stderr.strip()
    print(f"  [WARN] push rejected: {stderr[:120]}")
    if "[rejected]" not in stderr and "non-fast-forward" not in stderr.lower():
        print(f"  [FAIL] push 失败（非分叉原因），跳过")
        return False

    # Agent 分支是单写者，分叉时 force-with-lease 安全
    print("  [WARN] 分支分叉，尝试 force-with-lease...")
    r2 = _run(f"git push --force-with-lease origin {branch}")
    if r2.returncode == 0:
        print(f"  [OK] pushed {branch} (--force-with-lease)")
        return True

    print(f"  [WARN] force-with-lease 也失败: {r2.stderr.strip()[:120]}")
    r3 = _run(f"git push --force origin {branch}")
    if r3.returncode != 0:
        print(f"  [FAIL] force push 也失败: {r3.stderr.strip()[:120]}")
        return False
    print(f"  [OK] pushed {branch} (--force)")
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if len(sys.argv) < 3:
        print("Usage: task_done.py <username> <taskID> [IMP序号] [VFY轮数] [--project-root <dir>] [--task-desc <desc>] [--do-commit] [--format shell]")
        sys.exit(1)

    whoami = sys.argv[1]
    task_id = sys.argv[2]
    imp_n = sys.argv[3] if len(sys.argv) > 3 else "1"
    vfy_n = sys.argv[4] if len(sys.argv) > 4 else "1"
    start_round = 1
    do_commit = "--do-commit" in sys.argv

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
    output_dir = None
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
        elif arg == "--start-round" and i + 1 < len(sys.argv):
            start_round = int(sys.argv[i + 1])

    if not project_root:
        project_root = find_project_root()
    if not output_dir:
        output_dir = os.getcwd()

    print(f"=== 任务完成: {task_id} ===")

    # ── commit + push ──
    if do_commit:
        commit_title = task_desc or task_id
        loop_dir = os.path.join(output_dir, ".loop-engineering", "tasks", task_id)
        imp_rounds = _collect_round_files(loop_dir, "imp-output-r*.md")
        vfy_rounds = _collect_round_files(loop_dir, "vfy-output-r*.md")

        # 只收集本次执行（>= start_round）的轮次
        all_rounds = sorted(set(list(imp_rounds.keys()) + list(vfy_rounds.keys())))
        my_rounds = [r for r in all_rounds if r >= start_round]
        if my_rounds:
            final_round = my_rounds[-1]
        else:
            final_round = 0

        commit_msg = f"[{task_id}] {commit_title}\n\n"

        for r in my_rounds:
            commit_msg += f"## Round {r}\n\n"

            # IMP
            imp_content = ""
            if r in imp_rounds:
                imp_content = _read_output_file(imp_rounds[r])
            if imp_content:
                if r < final_round:
                    trimmed = _trim_imp_for_earlier_round(imp_content)
                    if trimmed:
                        commit_msg += "### IMP\n\n" + trimmed
                else:
                    commit_msg += "### IMP\n\n" + imp_content + "\n\n"

            # VFY
            vfy_content = ""
            if r in vfy_rounds:
                vfy_content = _read_output_file(vfy_rounds[r])
            if vfy_content:
                commit_msg += "### VFY\n\n" + vfy_content + "\n\n"

        if my_rounds:
            commit_msg += f"---\nIMP{len([r for r in my_rounds if r in imp_rounds])} VFY{len([r for r in my_rounds if r in vfy_rounds])}"

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
            pushed = _push_branch(branch)
        else:
            print("  (无改动，跳过 commit)")
            pushed = True

        if not pushed:
            print("  [FAIL] 未能推送到远程，跳过 tasks.md 更新和通知")
            return

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
    meta_text = f"{now} IMP{imp_n} VFY{vfy_n} PASS"
    modified, _, _ = update_task(
        os.path.join(project_root, "tasks.md"), task_id,
        status="x", append_meta=meta_text, assignee=whoami,
        if_status_in=(" ", "~", "r"),
    )
    status = "[x]" if modified else "未匹配"
    print(f"tasks.md: {task_id} → {status}")


if __name__ == "__main__":
    main()
