---
name: task-add
description: >
  往根 tasks.md 添加任务。支持三种方式：直接描述、用 OpenSpec 新建 change、指定已有 OpenSpec change。
user_invocable: true
---

# Task Add（任务添加）

把用户意图转成 `tasks.md` 中的任务条目。

## 模式选择

先根据用户输入判断走哪种模式：

- 明确提到 OpenSpec change 名称（如"把 xxx change 加到任务"）→ **模式 3**
- 明确提到"新建 change"、"创建 OpenSpec" → **模式 2**
- 明确描述了具体任务内容（做什么 + 怎么验证）→ **模式 1**
- **无法判断时**，用 **AskUserQuestion** 让用户选择：

```json
{
  "header": "添加方式",
  "multiSelect": false,
  "options": [
    {"label": "直接添加", "description": "输入任务描述，直接追加到 tasks.md"},
    {"label": "新建 OpenSpec change", "description": "先用 openspec-new-change 创建完整 change，再添加任务"},
    {"label": "指定已有 change", "description": "选择已有的 OpenSpec change 添加为任务"}
  ],
  "question": "选择任务添加方式："
}
```

## 通用前置步骤

每次添加前：
1. `git config user.name` 获取当前用户
2. 读 `tasks.md`，若文件不存在则创建：
   ```markdown
   # Tasks

   > 约定: 任务按日期分组，同天内按优先级从上到下排列

   ## YYYY-MM-DD

   ```
3. **去重检查**：grep `tasks.md` 中是否已存在相同描述的条目（忽略 `[ ]` / `[x]` 状态标记）。若存在则提示用户"任务已存在"并停止，不重复添加。
4. **定位日期分组**：取当天日期，若 `## YYYY-MM-DD` 段落不存在则创建。
5. **生成 task_id**：用 `python -c "from loop_engineering.task_id import generate_task_id; print(generate_task_id('<描述>'))"` 生成 8 位十六进制 task_id。

## 模式 1: 直接添加

用户说"加个任务"。

1. **描述质量门控**——必须同时满足两个要素，缺一则追问用户：
   - **做什么**：具体可执行的动作描述（不是"修 bug"、"优化"等模糊词）
   - **怎么验证**：验收条件，如"编译 0 error"、"read_console 无异常"、"游戏内 X 功能正常"
2. 在当天的日期分组末尾追加：
   ```markdown
   - [ ] <描述> (→ <user>) [<task_id>]
   ```
3. 不 commit，留给用户自己提交

## 模式 2: OpenSpec 新建 change

用户说"新建 change 和 task"。

1. 调用 `openspec-new-change` skill，和用户交互梳理需求 → 生成完整的 change（包含 spec、design、tasks.md）
2. **确保已提交**：change 文件生成后必须 commit（含 proposal.md、design.md、specs/、tasks.md），否则 agent worktree 读不到这些文件。不要求 push，但至少本地 commit。
3. change 生成并提交后，去重检查通过后，生成 task_id（用 change-name 作为描述），在当天日期分组末尾追加：
   ```markdown
   - [ ] <change-name> (→ <user>) [<task_id>]
   ```
4. 告诉用户 change 已生成，可以去 `openspec/changes/<name>/tasks.md` 看详情

## 模式 3: 指定已有 OpenSpec change

用户说"把 xxx change 加到我的任务"，或用户选了模式 3。

**确定 change 名称**：

- 用户已指定名称 → 直接使用
- 用户没指定 → 扫描 `openspec/changes/` 下所有目录，读取每个 `proposal.md` 的第一行（通常是标题）作为描述，用 **AskUserQuestion** 让用户选择：

```json
{
  "header": "选择 Change",
  "multiSelect": false,
  "options": [
    {"label": "<change-name>", "description": "proposal.md 第一行摘要"},
    ...
  ],
  "question": "选择要添加的 OpenSpec change："
}
```

选定 change 后：

1. 确认 `openspec/changes/<name>/` 存在
2. **确保已提交**：检查 change 文件是否已 commit（`git status` 确认 `openspec/changes/<name>/` 不在 untracked/modified 中）。未提交则先 commit 再继续。不要求 push，但至少本地 commit。
3. **OpenSpec 状态检查**：读 `openspec/changes/<name>/tasks.md`，统计 `[ ]` 和 `[x]` 数量：
   - **全完成**（0 个 `[ ]`）→ 警告用户"该 change 所有子任务已完成，无需添加"，用 **AskUserQuestion** 确认是否仍要添加：
     ```json
     {
       "header": "仍要添加",
       "multiSelect": false,
       "options": [
         {"label": "仍要添加", "description": "忽略警告，继续添加任务"},
         {"label": "取消", "description": "不添加此任务"}
       ],
       "question": "该 change 所有子任务已完成。是否仍要添加？"
     }
     ```
   - **部分完成**（有 `[ ]` 有 `[x]`）→ 正常添加，输出中标注进度
   - **全未开始**（全部 `[ ]`）→ 正常添加
4. 去重检查通过后，生成 task_id（用 change-name 作为描述），在当天日期分组末尾追加：
   ```markdown
   - [ ] <change-name> (→ <user>) [<task_id>]
   ```

## 输出

追加后输出队列概览：

```markdown
## 已添加
**条目**: `- [ ] <条目> (→ <user>) [<task_id>]`
**来源**: 直接添加 / OpenSpec 新建 / 已有 change
**进度**: <change 已完成子任务数>/<总子任务数>（仅模式 3 有进度时显示）
**队列**: 位置 N/M，前面还有 K 个待办任务
```
