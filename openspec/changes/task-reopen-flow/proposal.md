## Why

任务完成后，用户可能发现问题需要修改。当前只能手动改 tasks.md 状态或新建任务——没有标准化的"返工"流程。需要让任务支持重新打开，在已有实现基础上继续修改，同时保留完整的迭代历史。

## What Changes

- 新增 `[r]`（reopen）任务状态，与 `[ ]` 一样被 task-runner 拾取
- `task_pick` 识别 `[r]` 状态，自动查找已有 agent 分支，输出 `reopen=true`
- task-runner `reopen=true` 时 checkout 已有分支（不从 master fork 新分支）
- implementer prompt 注入旧 commit 报告 + reopen 反馈
- commit message 新增 `## 本轮反馈` 节
- `GET /api/tasks/{task_id}/report` 改为全量返回所有轮次报告
- 前端：reopen modal（编辑目标 + 反馈）、`[r]` 状态徽标、报告多轮次 tab 切换
- tasks.md 缩进行支持 reopen 反馈内容

## Capabilities

### New Capabilities

- `task-reopen-state`: `[r]` 状态定义、tasks.md 解析、状态流转
- `task-reopen-pick`: task_pick 识别 `[r]` 并发现已有分支
- `task-reopen-implementer`: implementer 获取历史报告和反馈上下文
- `task-reopen-report`: 报告 API 全量返回 + 前端多轮次查看

### Modified Capabilities

<!-- No existing specs to modify -->

## Impact

| 层面 | 影响 |
|------|------|
| tasks.md 格式 | 新增 `[r]` 状态字符、缩进行反馈 |
| task_pick.py | 正则匹配扩展 `[ r]`、git branch 查询逻辑 |
| task-runner SKILL.md | Step 2 分支策略、Step 3 implementer prompt 模板 |
| task_done.py | [r]→[x] 状态更新逻辑适配 |
| tasks API | 新增 `PUT /{task_id}/reopen`、report 端点改全量 |
| 前端 | `_tasks_items.html` reopen modal + `[r]` 徽标 + 报告 tab |
| commit 格式 | 新增 `## 本轮反馈` 节 |
