---
name: task-add
description: >
  往根 tasks.md 添加任务。支持三种方式：直接描述、用 OpenSpec 新建 change、指定已有 OpenSpec change。
user_invocable: true
---

# Task Add（任务添加）

把用户意图转成 `tasks.md` 中的任务条目。三种模式：

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

## 模式 1: 直接添加

用户说"加个任务"。

1. **描述质量门控**——必须同时满足两个要素，缺一则追问用户：
   - **做什么**：具体可执行的动作描述（不是"修 bug"、"优化"等模糊词）
   - **怎么验证**：验收条件，如"编译 0 error"、"read_console 无异常"、"游戏内 X 功能正常"
2. 在当天的日期分组末尾追加：
   ```markdown
   - [ ] <描述> (→ <user>)
   ```
3. 不 commit，留给用户自己提交

## 模式 2: OpenSpec 新建 change

用户说"新建 change 和 task"。

1. 调用 `openspec-new-change` skill，和用户交互梳理需求 → 生成完整的 change（包含 spec、design、tasks.md）
2. change 生成后，去重检查通过后，在当天日期分组末尾追加：
   ```markdown
   - [ ] <change-name> (→ <user>)
   ```
3. 告诉用户 change 已生成，可以去 `openspec/changes/<name>/tasks.md` 看详情

## 模式 3: 指定已有 OpenSpec change

用户说"把 xxx change 加到我的任务"。

1. 确认 `openspec/changes/<name>/` 存在
2. **OpenSpec 状态检查**：读 `openspec/changes/<name>/tasks.md`，统计 `[ ]` 和 `[x]` 数量：
   - **全完成**（0 个 `[ ]`）→ 警告用户"该 change 所有子任务已完成，无需添加"，询问是否仍要添加
   - **部分完成**（有 `[ ]` 有 `[x]`）→ 正常添加，输出中标注进度
   - **全未开始**（全部 `[ ]`）→ 正常添加
3. 去重检查通过后，在当天日期分组末尾追加：
   ```markdown
   - [ ] <change-name> (→ <user>)
   ```

## 输出

追加后输出队列概览：

```markdown
## 已添加
**条目**: `- [ ] <条目> (→ <user>)`
**来源**: 直接添加 / OpenSpec 新建 / 已有 change
**进度**: <change 已完成子任务数>/<总子任务数>（仅模式 3 有进度时显示）
**队列**: 位置 N/M，前面还有 K 个待办任务
```
