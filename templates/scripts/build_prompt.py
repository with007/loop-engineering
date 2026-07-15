#!/usr/bin/env python3
"""Build IMP/VFY sub-agent prompts. Zero-dependency, reads loop-config.yaml for paths.

Usage:
  python .claude/scripts/build_prompt.py imp --desc "..." --task-id xxxx --branch [--round 1] [--open-spec] [--reopen] [--user-feedback "..."] --project-root <dir>
  python .claude/scripts/build_prompt.py vfy --desc "..." --task-id xxxx --branch [--round 1] [--open-spec] [--user-feedback "..."] --project-root <dir>
"""
import argparse, os, sys, yaml


def _find_config():
    p = os.path.abspath(os.getcwd())
    for _ in range(10):
        for name in [".loop-engineering/loop-config.yaml", "loop-config.yaml"]:
            path = os.path.join(p, name)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return yaml.safe_load(f)
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return {}

CFG = _find_config()
AGENT_WS = CFG.get("agent", {}).get("workspace", os.getcwd())
AGENT_DIR = AGENT_WS + "/loop-engineering"
PROJECT_ROOT = None  # set by CLI --project-root


def _tp(task_id, filename):
    """绝对路径：{project_root}/.loop-engineering/tasks/{task_id}/{filename}"""
    root = PROJECT_ROOT.replace('\\', '/')
    return root + "/.loop-engineering/tasks/" + task_id + "/" + filename


def _tp_dir(task_id):
    """绝对路径：{project_root}/.loop-engineering/tasks/{task_id}/"""
    root = PROJECT_ROOT.replace('\\', '/')
    return root + "/.loop-engineering/tasks/" + task_id + "/"


# -- prompt blocks -----------------------------------------------------------

def _wd_imp(branch):
    return (
        "## 工作目录\n"
        "你必须在 agent worktree 工作：**" + AGENT_DIR + "**（不是主工程目录）。\n\n"
        "```bash\n"
        "cd " + AGENT_DIR + "\n"
        "git checkout " + branch + "\n"
        "pwd  # 必须输出 " + AGENT_DIR + "\n"
        "```"
    )


def _wd_vfy(branch):
    return (
        "## 工作目录\n"
        "你必须在 agent worktree 工作：**" + AGENT_DIR + "**（不是主工程目录）。\n\n"
        "```bash\n"
        "cd " + AGENT_DIR + "\n"
        "git log --oneline " + branch + " -5  # 确认分支存在\n"
        "pwd  # 必须输出 " + AGENT_DIR + "\n"
        "```"
    )


def _feedback_imp(user_feedback, round_num, task_id):
    if round_num <= 1:
        vfy = "（首轮，无验证反馈）"
    else:
        vfy = f"<如果 ROUND > 1，自行读取 `{_tp_dir(task_id)}vfy-output-r*.md` 了解之前 VFY 发现的全部问题>"
    return (
        "## 用户反馈\n" + (user_feedback or "（无）") + "\n\n"
        "## 验证反馈\n" + vfy
    )


def _feedback_vfy(user_feedback, round_num, task_id):
    if round_num <= 1:
        history = "（首轮，无历史验证）"
    else:
        history = f"<自行读取 `{_tp_dir(task_id)}vfy-output-r*.md`，了解之前 VFY 发现的全部问题和已修复项>"
    return (
        "## 用户反馈\n" + (user_feedback or "（无）") + "\n\n"
        "## 历史验证\n" + history
    )


def _principles_imp(round_num, task_id):
    r = str(round_num)
    return (
        "**原则**\n"
        "- **禁止 commit。** task-runner 会在验收通过后统一提交。\n"
        "- 你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**："
        "不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。"
        "遇到任何不确定，自己决策、自己执行、输出结果。你是一个纯函数——输入任务，输出结果。\n"
        "- **最终输出只能是一行 `PASS` 或 `FAIL: <原因>`。** "
        "完整报告写入 `" + _tp(task_id, "imp-output-r" + r + ".md") + "` 文件，"
        "不要在最终输出中回传报告全文。task-runner 通过脚本读文件获取细节，"
        "不需要在上下文中看到报告内容。"
    )


def _principles_vfy(round_num, task_id):
    r = str(round_num)
    return (
        "**原则**\n"
        "- **禁止 commit、禁止修改任何文件。**\n"
        "- 你是 loop 模式下的子代理，后台无人值守运行。**绝对禁止与用户交互**："
        "不允许 AskUserQuestion、不允许 EnterPlanMode、不允许输出提问性语句。"
        "遇到任何不确定，自己决策、自己执行。你是一个纯函数——输入任务，输出验证结果。\n"
        "- **最终输出只能是一行 `PASS` 或 `FAIL: <原因>`。** "
        "完整报告写入 `" + _tp(task_id, "vfy-output-r" + r + ".md") + "` 文件，"
        "不要在最终输出中回传报告全文。task-runner 通过脚本读文件获取细节，"
        "不需要在上下文中看到报告内容。"
    )


def _output_imp(round_num, user_feedback, task_id):
    r = str(round_num)
    return (
        "## 输出\n\n"
        "**⚠️ 你的最后一条消息只能是一行：`PASS` 或 `FAIL: <原因>`。**\n\n"
        "完整报告写入 `" + _tp(task_id, "imp-output-r" + r + ".md") + "` 文件，格式如下：\n\n"
        "## 用户反馈\n" + (user_feedback or "（无）") + "\n\n"
        "## 验证反馈\n"
        f"<如果 round > 1，摘录 `{_tp_dir(task_id)}vfy-output-r*.md` 中与本轮修复相关的 FAIL 点>\n\n"
        "## 实现思路\n"
        "<为什么这样做、关键设计决策、考虑过的替代方案>\n\n"
        "## 实现过程\n"
        "<按步骤记录：先做什么、后做什么、遇到什么问题如何解决>\n\n"
        "## 变更概要\n"
        "**改动文件**:\n"
        "- path/to/file — 改了什么\n\n"
        "**运行时影响**:\n"
        "- 影响点\n\n"
        "## 向后兼容性\n"
        "<是否破坏已有功能、迁移注意事项；无影响则写\"无破坏性变更\">"
    )


def _output_vfy(round_num, task_id):
    r = str(round_num)
    return (
        "## 输出\n\n"
        "**⚠️ 你的最后一条消息只能是一行：`PASS` 或 `FAIL: <原因>`。** "
        "完整报告已写入 `" + _tp(task_id, "vfy-output-r" + r + ".md") + "`，报告格式遵循 `/loop-verify` 的规定。"
    )


# -- builders ----------------------------------------------------------------

def build_imp(desc, task_id, branch, round_num, user_feedback, open_spec, reopen):
    open_label = "（OpenSpec）" if open_spec else ""
    header = (
        "## 任务" + open_label + "\n"
        + desc + "\n"
        "taskID: " + task_id + "\n"
        "reopen: " + ("true" if reopen else "false")
    )

    if open_spec:
        flow = (
            "**流程**\n"
            "1. 读 openspec/changes/" + desc + "/proposal.md 理解目标与范围\n"
            "2. 读 openspec/changes/" + desc + "/design.md 理解架构决策\n"
            "3. 读 openspec/changes/" + desc + "/tasks.md 获取子任务列表\n"
            "4. 读 openspec/changes/" + desc + "/specs/ 下各 spec 获取详细规格\n"
            "5. 按 openspec-apply-change 流程逐子任务实现\n"
            "6. 每个子任务完成后标记 openspec/changes/" + desc + "/tasks.md 中的 [ ] -> [x]\n"
            "7. 将完整报告写入 `" + _tp(task_id, "imp-output-r" + str(round_num) + ".md") + "`\n"
            "8. 最后输出一行：`PASS` 或 `FAIL: <原因>`"
        )
    else:
        flow = (
            "**流程**\n"
            "1. 理解任务描述，自行研究代码库，设计方案\n"
            "2. 读相关代码、模板、配置，理解现有架构和上下文\n"
            "3. 实现变更\n"
            "4. 将完整报告写入 `" + _tp(task_id, "imp-output-r" + str(round_num) + ".md") + "`\n"
            "5. 最后输出一行：`PASS` 或 `FAIL: <原因>`"
        )

    sections = [header, "", _wd_imp(branch)]

    if reopen:
        sections.extend([
            "", "## 历史报告",
            "以下为上次实现的 commit message，请理解已有实现后在此基础上修改：",
            "", "<git log -1 --format=%B 的输出>",
        ])

    sections.extend([
        "", _feedback_imp(user_feedback, round_num, task_id),
        "", "---",
        "", "## 你的工作",
        "", _principles_imp(round_num, task_id),
        "", flow,
        "", "## 分支", branch,
        "", _output_imp(round_num, user_feedback, task_id),
    ])

    return "\n".join(sections)


def build_vfy(desc, task_id, branch, round_num, user_feedback, open_spec):
    open_label = "（OpenSpec）" if open_spec else ""
    header = (
        "## 任务" + open_label + "\n"
        + desc + "\n"
        "taskID: " + task_id
    )

    flow = (
        "**流程**\n"
        "1. IMP 不 commit，变更在 working tree。用 `git status --short` 看全貌（含新增文件），`git diff` + `git diff --cached` 看具体内容，对照任务描述理解\n"
        "2. 如需了解历史上下文，可用 `git log " + branch + " --not master --oneline --grep=\"" + task_id + "\"` 查看本任务相关的历史 commit，但**验证对象是 working tree diff，不是已 commit 的内容**\n"
        "3. 读历史验证文件（`" + _tp_dir(task_id) + "vfy-output-r*.md`），了解之前的验证结果和已修复问题\n"
        "4. 按 `/loop-verify` 的方法论执行验证：表面识别 -> 驱动 -> 探测 -> 报告\n"
        "5. 将完整验证报告写入 `" + _tp(task_id, "vfy-output-r" + str(round_num) + ".md") + "`\n"
        "6. 最后输出一行：`PASS` 或 `FAIL: <原因>`"
    )

    sections = [
        header, "",
        _wd_vfy(branch), "",
        _feedback_vfy(user_feedback, round_num, task_id),
        "", "---",
        "", "## 你的工作（只能验证，不能改代码）",
        "", _principles_vfy(round_num, task_id),
        "", flow,
        "", _output_vfy(round_num, task_id),
    ]

    return "\n".join(sections)


# -- CLI ---------------------------------------------------------------------

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="Build IMP/VFY sub-agent prompt")
    parser.add_argument("type", choices=["imp", "vfy"])
    parser.add_argument("--desc", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--user-feedback", default="")
    parser.add_argument("--open-spec", action="store_true")
    parser.add_argument("--reopen", action="store_true")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    global PROJECT_ROOT
    PROJECT_ROOT = args.project_root

    if args.type == "imp":
        print(build_imp(args.desc, args.task_id, args.branch,
                        args.round, args.user_feedback,
                        args.open_spec, args.reopen))
    else:
        print(build_vfy(args.desc, args.task_id, args.branch,
                        args.round, args.user_feedback,
                        args.open_spec))

if __name__ == "__main__":
    main()
