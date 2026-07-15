## Context

任务列表页面已有报告模态框（report modal）和重开模态框（reopen modal），都是用 Alpine.js `x-data` + `CustomEvent` 模式实现。本次新增详情面板，沿用相同技术栈。

数据层已就绪：`taskhelper.load_state()` 可直接读取 state.json，所有已迁移任务都有完整数据。

## Goals / Non-Goals

**Goals:**
- 点击任务卡片打开详情面板，展示 state.json 中的完整信息
- 面板支持连续浏览（点击不同任务无需关闭重开）
- 与现有报告模态框共存（面板里可触发报告查看）

**Non-Goals:**
- 不在卡片上添加时间信息（保持卡片简洁）
- 不修改 `parse_tasks()`/`list_tasks()`（已在上一个 change 中完成）
- 不修改现有报告模态框

## Decisions

### 1. 侧面板而非模态框

**选择**: 右侧滑入面板（420px, `x-transition` 动画）

**理由**: 详情是结构化元数据，扫一眼就够，不需要独占屏幕。侧面板让任务列表保持可见，支持快速浏览多个任务。与报告模态框（markdown 长文需沉浸阅读）各司其职。

**备选**: 模态框 — 与报告模态框风格一致但遮盖列表，浏览效率低。

### 2. 整个卡片可点击

**选择**: 卡片外层 `div` 加 `onclick="viewDetail(taskId)"`，操作按钮加 `event.stopPropagation()`

**理由**: 用户直觉是"点任务 = 看详情"。按钮已有各自的事件处理，隔离简单。

**备选**: 仅信息区可点击 — 需要额外 CSS 提示点击范围，容易误触。

### 3. 数据从 load_state() 获取

**选择**: 新增 `GET /api/tasks/{task_id}/detail`，直接返回 `taskhelper.load_state()` 的结果

**理由**: `load_state()` 已有 state.json → 最小 state 回退逻辑，无需额外处理。JSON 结构完整，前端直接渲染。

### 4. 面板在 HTMX 轮询区域之外

**选择**: 面板 Alpine.js 组件放在 `tasks.html` 最外层，不属于 `#tasks-list-wrap`

**理由**: `_tasks_items.html` 会被 HTMX 轮询刷新，面板放在其中会导致 DOM 替换时丢失状态。放在外层确保面板独立。

## Risks / Trade-offs

- **[Risk]** 大量任务同时有反馈时，面板内容可能很长 → 面板设置 `overflow-y: auto`，自然滚动
- **[Risk]** Alpine.js `x-transition` 在快速连续点击时可能动画不同步 → 面板打开时 `fetch` 新数据即可，无排队问题
- **[Trade-off]** 面板不显示 tasks.md 的 meta 文本（已从 state.json 移除）→ 所有信息在 state.json 中更结构化
