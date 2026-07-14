## Context

当前任务完成后（`[x]`）没有标准的"返工"入口。用户发现问题需要手动改 tasks.md 或新建任务。需要新增 `[r]`（reopen）状态，让任务在已有分支上继续修改。

相关影响范围：tasks.md 解析、task_pick 分支发现、task-runner 分支策略、implementer prompt、commit 格式、报告 API、前端 UI。

## Goals / Non-Goals

**Goals:**
- `[r]` 状态被 task_pick 识别，自动查找已有分支
- reopen 时用户在旧分支基础上修改，不从 master fork
- implementer 获取旧 commit 报告 + reopen 反馈作为上下文
- commit message 记录每次 reopen 的反馈
- 报告 API 返回所有轮次，前端支持切换查看

**Non-Goals:**
- 不改变 `[ ]` `[~]` `[x]` 的现有行为
- 不处理 master 同步（合入时解决）
- 不自动清理旧远程分支

## Decisions

### 1. 状态设计：`[r]` 替代 meta 标记

状态字符只回答"task-runner 要不要处理它"：
- `[ ]` = 待办，从 master fork 新分支
- `[~]` = 进行中
- `[x]` = 已完成
- `[r]` = 需返工，在已有分支上修改

**替代方案**：用 meta 字段（如 `🔄`）标记。不选——meta 字段已拥挤，正则解析更复杂，前端渲染需额外判断。

### 2. 反馈存储：缩进行

tasks.md 中 `[r]` 行下方的缩进行作为反馈：

```markdown
- [r] 翻译tab页标题为中文 (→ withg) [0d3e52c8] — IMP1 VFY1 PASS
  上次漏了英文环境回退
  日文也不行
```

**替代方案**：独立文件（`.loop-engineering/reopen/{task_id}.md`）。不选——需配对清理，人没法一眼看全貌。

### 3. 分支发现：git branch 查询

task_pick 遇到 `[r]` 时，用 `git branch -a --list "agent/{whoami}/{task_id}-*" --sort=-committerdate` 查找已有分支，取最新。Step 0 已执行 `git fetch --prune`，本地 refs 是最新的，找不到即说明分支不存在。此时尝试 reflog 恢复，仍找不到则跳过（打 stderr），不降级为 `[ ]`。

### 4. 分支策略：直接 checkout，不 rebase

task-runner `reopen=true` 时执行 `git checkout <BRANCH>`，不从 master fork 也不 rebase。master 同步留给合入时处理。

### 5. Implementer 上下文注入

task-runner Step 3 派发前：
1. `git log -1 --format=%B` 获取旧 commit 报告
2. 解析 tasks.md 反馈缩进行
3. 拼入 implementer prompt 的"历史报告"和"本轮反馈"节

### 6. Commit message 新节

在现有格式的"实现思路"前新增 `## 本轮反馈` 节。implementer 从 prompt 上下文填充。

### 7. 报告 API 全量返回

`GET /api/tasks/{task_id}/report` 去掉 `-1` 限制，返回 `{"reports": [{commit_hash, date, imp_round, body}, ...]}`。前端用 tab 切换轮次，默认显示最新。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 旧分支被手动删除 | task_pick 跳过该任务，打 stderr 告警 |
| 同 task_id 有多个分支 | `--sort=-committerdate` 取最新 |
| 多轮 reopen 后 tasks.md 缩进行过长 | 反馈不追加历史，只保留本轮 |

## Open Questions

- task_done 写回时 `[r]` 变为 `[x]`，历史 IMP/VFY 记录保留格式待定（当前暂追加：`IMP1 VFY1 PASS · IMP2 VFY1 PASS`）
