"""Loop Engineering 运行日志.

结构化记录每次 implement/verify 事件。一个文件一个事件。
存储位置: .loop-engineering/runs/
"""

import os
import json
from datetime import datetime, timezone
from loop_engineering.utils import atomic_write


def _runs_dir(project_root):
    return os.path.join(project_root, ".loop-engineering", "runs")


def write_run_log(project_root, entry):
    """写入一条 run log.

    entry 必须包含: task_id, imp_round, vfy_round, phase, result
    自动添加 started/completed 时间戳。
    """
    runs = _runs_dir(project_root)
    os.makedirs(runs, exist_ok=True)

    # 自动时间戳
    now = datetime.now(timezone.utc).isoformat()
    entry.setdefault("version", 1)
    entry.setdefault("started", now)
    entry.setdefault("completed", now)
    entry.setdefault("whoami", "")
    entry.setdefault("task_desc", "")
    entry.setdefault("branch", "")
    entry.setdefault("summary", "")
    entry.setdefault("files_changed", [])
    entry.setdefault("tests", [])
    entry.setdefault("fail_reason", None)
    entry.setdefault("open_spec", False)
    entry.setdefault("hint", None)

    fname = f"{entry['task_id']}--IMP{entry['imp_round']}--VFY{entry['vfy_round']}.json"
    fpath = os.path.join(runs, fname)

    content = json.dumps(entry, indent=2, ensure_ascii=False, default=str)
    atomic_write(fpath, content)

    return fpath


def list_runs(project_root, whoami=None, result=None, days=None, limit=50):
    """列出 run log 文件，支持过滤。

    返回按 completed 时间倒序排列的 entry 列表。
    """
    runs = _runs_dir(project_root)
    if not os.path.isdir(runs):
        return []

    entries = []
    cutoff = None
    if days:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for fname in os.listdir(runs):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(runs, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                entry = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue  # skip corrupt files

        # 过滤
        if whoami and entry.get("whoami") != whoami:
            continue
        if result and entry.get("result") != result:
            continue
        if cutoff:
            try:
                completed = datetime.fromisoformat(entry.get("completed", ""))
                if completed < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        entries.append(entry)

    # 按 completed 倒序
    entries.sort(key=lambda e: e.get("completed", ""), reverse=True)
    return entries[:limit]


def get_pass_rate(project_root, days=7):
    """计算指定天数内的 PASS 率。

    返回 (pass_count, total_count, rate)。
    """
    entries = list_runs(project_root, days=days, limit=10000)
    # 只统计 verify 阶段
    verify_entries = [e for e in entries if e.get("phase") == "verify"]
    total = len(verify_entries)
    if total == 0:
        return 0, 0, 0.0
    passed = sum(1 for e in verify_entries if e.get("result") == "PASS")
    return passed, total, passed / total
