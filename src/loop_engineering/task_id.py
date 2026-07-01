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


# ── TaskLine: tasks.md 统一解析 ──

_TASK_LINE_RE = re.compile(
    r'^- \[(.)\]\s+'             # checkbox: - [x]
    r'(.+?)'                      # description (non-greedy)
    r'(?:\s+\(→\s*(\w+)\))?'     # optional assignee: (→ whoami)
    r'(?:\s+\[([a-f0-9]{8})\])?' # optional task_id: [xxxxxxxx]
    r'(?:\s+—\s+(.+))?'          # optional meta: — text
    r'$'
)


class TaskLine:
    """tasks.md 中单行任务的解析和格式化。

    字段:
        status: " " (pending), "~" (in_progress), "x" (done), "r" (reopen)
        description: 任务描述文本
        assignee: 执行人（可选）
        task_id: 8 位十六进制 ID（可选）
        meta: 运行记录（可选，如 "14:30 IMP1 VFY1 PASS"）
        feedback: 缩进跟随的反馈行列表（不参与 format）
    """

    __slots__ = ("status", "description", "assignee", "task_id", "meta", "feedback")

    def __init__(self, status=" ", description="", assignee="", task_id="", meta="", feedback=None):
        self.status = status
        self.description = description
        self.assignee = assignee
        self.task_id = task_id
        self.meta = meta
        self.feedback = feedback if feedback is not None else []

    @classmethod
    def parse(cls, line: str):
        """从 tasks.md 行解析 TaskLine。非任务行返回 None。

        >>> TaskLine.parse("- [ ] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS")
        TaskLine(status=' ', description='Fix login', assignee='with', task_id='a1b2c3d4', meta='14:30 IMP1 VFY1 PASS')
        >>> TaskLine.parse("- [ ] Fix login")
        TaskLine(status=' ', description='Fix login')
        >>> TaskLine.parse("# Tasks")
        None
        """
        m = _TASK_LINE_RE.match(line)
        if not m:
            return None
        return cls(
            status=m.group(1),
            description=m.group(2).strip(),
            assignee=m.group(3) or "",
            task_id=m.group(4) or "",
            meta=m.group(5) or "",
        )

    def format(self) -> str:
        """序列化为 tasks.md 规范格式。parse(format(x)) == x 自反性。

        >>> tl = TaskLine(' ', 'Fix login', 'with', 'a1b2c3d4', '14:30 IMP1 VFY1 PASS')
        >>> tl.format()
        '- [ ] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS'
        """
        parts = [f"- [{self.status}] {self.description}"]
        if self.assignee:
            parts.append(f" (→ {self.assignee})")
        if self.task_id:
            parts.append(f" [{self.task_id}]")
        if self.meta:
            parts.append(f" — {self.meta}")
        return "".join(parts)

    def __repr__(self):
        fields = [f"status={self.status!r}"]
        if self.description:
            fields.append(f"description={self.description!r}")
        if self.assignee:
            fields.append(f"assignee={self.assignee!r}")
        if self.task_id:
            fields.append(f"task_id={self.task_id!r}")
        if self.meta:
            fields.append(f"meta={self.meta!r}")
        return f"TaskLine({', '.join(fields)})"

    def __eq__(self, other):
        if not isinstance(other, TaskLine):
            return NotImplemented
        return (self.status == other.status and
                self.description == other.description and
                self.assignee == other.assignee and
                self.task_id == other.task_id and
                self.meta == other.meta)


# ── 反馈行工具 ──

# 匹配缩进行（2+ 空格后接非空白字符），用于识别反馈行
FEEDBACK_LINE_RE = re.compile(r'^\s{2,}\S')

# 匹配 IMP 反馈标题: "## IMP{N} 反馈"（允许前导空白）
_IMP_HEADER_RE = re.compile(r'^\s*##\s+IMP(\d+)\s+反馈')


def _count_existing_imp(lines_slice):
    """统计给定行范围内已有的最大 IMP 编号，返回整数。无标题则返回 0。"""
    max_n = 0
    for line in lines_slice:
        m = _IMP_HEADER_RE.match(line)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n


def _find_task_range(lines, task_id):
    """查找指定 task_id 在 lines 中的起始行索引和结束行索引。

    返回 (task_line_idx, next_task_idx):
        task_line_idx: 任务行索引（checkbox 行），未找到时 None
        next_task_idx: 下一个任务行或 EOF 的索引

    如果 task_id 未找到，task_line_idx 为 None。
    """
    task_line_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^- \[(.)\]\s+', line):
            if parse_task_id(line) == task_id:
                task_line_idx = i
                break
    if task_line_idx is None:
        return None, len(lines)

    # 找下一个任务行
    next_task_idx = len(lines)
    for i in range(task_line_idx + 1, len(lines)):
        if re.match(r'^- \[(.)\]\s+', lines[i]):
            next_task_idx = i
            break
    return task_line_idx, next_task_idx


def write_feedback_to_task(tasks_path, task_id, feedback_text):
    """向 tasks.md 中的指定任务写入反馈。

    格式:
      ## IMP{N+1} 反馈
      <反馈内容，每行 2 空格缩进>

    N 为已有 IMP 标题的最大编号，新反馈编号为 N+1。

    Args:
        tasks_path: tasks.md 的绝对路径
        task_id: 目标任务的 8 位十六进制 ID
        feedback_text: 反馈文本，可以是多行

    Returns:
        新反馈的 IMP 编号（整数）

    Raises:
        ValueError: task_id 未找到时
        FileNotFoundError: tasks_path 不存在时
    """
    import os
    if not os.path.exists(tasks_path):
        raise FileNotFoundError(f"tasks.md not found: {tasks_path}")

    with open(tasks_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    task_line_idx, next_task_idx = _find_task_range(lines, task_id)
    if task_line_idx is None:
        raise ValueError(f"Task [{task_id}] not found in {tasks_path}")

    # 统计已有 IMP 标题编号
    existing_imp = _count_existing_imp(lines[task_line_idx:next_task_idx])
    imp_num = existing_imp + 1

    # 构建反馈行
    new_lines = []
    if feedback_text.strip():
        new_lines.append(f"  ## IMP{imp_num} 反馈\n")
        for fl in feedback_text.strip().split('\n'):
            if fl.strip():
                new_lines.append(f"  {fl.strip()}\n")

    # 插入到任务行之后、下一个任务行之前
    if new_lines:
        # 如果任务行和下一个任务行之间已有反馈行，追加到末尾
        insert_at = next_task_idx
        for j, fl in enumerate(new_lines):
            lines.insert(insert_at + j, fl)
    else:
        return imp_num  # 空反馈，只返回编号

    with open(tasks_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    return imp_num


def parse_feedback_lines(lines, start_idx=0):
    """解析反馈行，返回 (feedback_list, end_idx)。

    feedback_list 中每个元素为 dict:
        {'imp_round': int, 'content': str}

    end_idx 指向下一个任务行或 EOF。

    注：此函数已提取但尚未被生产代码调用，留待后续 refactoring。
    """
    feedback = []
    current_imp = None
    current_content = []

    i = start_idx
    while i < len(lines):
        line = lines[i]
        m = _IMP_HEADER_RE.match(line)
        if m:
            # 遇到新 IMP 标题，保存上一个
            if current_imp is not None:
                feedback.append({
                    'imp_round': current_imp,
                    'content': '\n'.join(current_content).strip(),
                })
            current_imp = int(m.group(1))
            current_content = []
        elif FEEDBACK_LINE_RE.match(line) and current_imp is not None:
            # 缩进行 = 反馈内容
            current_content.append(line.strip())
        elif re.match(r'^- \[(.)\]\s+', line):
            # 遇到下一个任务行，停止
            break
        elif line.strip() == '' and current_imp is not None:
            # 空行保留在内容中
            pass
        i += 1

    # 保存最后一个 IMP
    if current_imp is not None:
        feedback.append({
            'imp_round': current_imp,
            'content': '\n'.join(current_content).strip(),
        })

    return feedback, i
