## 1. Tasks.md 状态扩展

- [x] 1.1 `_read_tasks` 正则扩展：匹配 `[r]` 状态，解析缩进行反馈
- [x] 1.2 任务列表 API 返回 `reopen` 状态（status 字段）
- [x] 1.3 新增 `PUT /api/tasks/{task_id}/reopen` 端点：`[x]` → `[r]` + 更新描述 + 写反馈缩进行

## 2. task_pick 适配

- [x] 2.1 task_pick 正则匹配 `[ r]`，识别 reopen 任务
- [x] 2.2 `git branch -a --list "agent/{whoami}/{task_id}-*" --sort=-committerdate` 查找已有分支
- [x] 2.3 输出增加 `reopen=true|false` 字段
- [x] 2.4 分支不存在时退化为新任务行为（`reopen=false`）

## 3. task-runner 适配

- [x] 3.1 SKILL.md Step 2：`reopen=true` 时 `git checkout <BRANCH>`（不 fork 新分支）
- [x] 3.2 SKILL.md Step 3 implementer prompt：注入 `## 历史报告`（旧 commit body）和 `## 本轮反馈`（缩进行）
- [x] 3.3 implementer 输出模板：新增 `## 本轮反馈` 节（在实现思路之前）
- [x] 3.4 setup.py SKILL_MD_TEMPLATE 同步更新

## 4. task_done 适配

- [x] 4.1 `[r]` → `[x]` 状态更新逻辑
- [x] 4.2 保留旧 IMP/VFY 记录，追加新记录（`IMP1 VFY1 PASS · IMP2 VFY1 PASS`）

## 5. 报告 API 多轮次

- [x] 5.1 `GET /api/tasks/{task_id}/report` 去掉 `-1`，返回全部匹配 commit
- [x] 5.2 响应格式改为 `{"reports": [{commit_hash, date, imp_round, body}, ...]}`

## 6. 前端

- [x] 6.1 `[r]` 任务显示"需返工"徽标（新颜色）
- [x] 6.2 已完成任务卡加"重新打开"按钮
- [x] 6.3 reopen modal：编辑任务目标 + 输入反馈
- [x] 6.4 报告 modal 支持多轮次 tab 切换
