"""Task ID 公共模块。

task_id 格式: md5(描述)[:8]，在 tasks.md 中以 [xxxxxxxx] 存储。
分支名格式: agent/<whoami>/<task_id>-<可读slug>
"""

import hashlib
import re


def generate_task_id(description: str) -> str:
    """从描述生成 task_id = md5 前 8 位（十六进制）."""
    return hashlib.md5(description.encode('utf-8')).hexdigest()[:8]


def make_readable_slug(description: str, max_len: int = 40) -> str:
    """从描述生成可读的 git 分支名后缀，保留中文。

    只去除 git 分支不接受的字符: \\ : ? * [ ] ~ ^ { } !
    空格替换为连字符。
    """
    # 取 " — " 之前的部分
    desc = re.split(r'\s+—\s+', description.strip())[0].strip()
    # 去掉 git 非法/问题字符
    desc = re.sub(r'[\\:?*\[\]~^{}!]', '', desc)
    # 空格转连字符
    desc = re.sub(r'\s+', '-', desc)
    # 压缩连续连字符
    desc = re.sub(r'-{2,}', '-', desc)
    # 不能以 . 开头或结尾，不能有 ..
    desc = re.sub(r'\.{2,}', '', desc)
    desc = re.sub(r'^\.|\.$', '', desc)
    # 去掉首尾连字符
    desc = re.sub(r'^-+|-+$', '', desc)
    result = desc[:max_len]
    # 如果全空了（极端情况），用纯 task 后缀
    if not result or len(result) < 1:
        result = 'task'
    return result


def parse_task_id(line: str) -> str or None:
    """从 tasks.md 行解析显式指定的 [xxxxxxxx] task_id。

    返回 8 位十六进制字符串，或 None（未指定）。
    """
    m = re.search(r'\[([a-f0-9]{8})\]', line)
    return m.group(1) if m else None


def extract_task_id_from_branch(branch_name: str) -> str or None:
    """从分支名提取 task_id。

    agent/with/a1b2c3d4-翻译tab → a1b2c3d4
    假设分支名最后一段的第一部分（第一个 - 之前）是 task_id。
    """
    basename = branch_name.split('/')[-1].strip()
    # 只有 md5（8 位十六进制，无连字符）→ 直接返回
    if re.match(r'^[a-f0-9]{8}$', basename):
        return basename
    # 格式: task_id-xxx → 取第一部分
    parts = basename.split('-', 1)
    return parts[0] if parts[0] else None


def make_branch_name(whoami: str, task_id: str, description: str) -> str:
    """构造 agent 分支名。

    agent/<whoami>/<task_id>-<可读slug>
    """
    slug = make_readable_slug(description)
    return f"agent/{whoami}/{task_id}-{slug}"

