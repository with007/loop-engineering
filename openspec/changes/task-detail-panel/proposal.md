## Why

任务列表目前只展示描述、分配人和状态，缺少时间维度的信息。用户想知道"这个任务什么时候创建的？""执行了几次？""每次花了多久？"——这些数据在 state.json 里都有，但没有展示界面。

## What Changes

- 新增 `GET /api/tasks/{task_id}/detail` 端点，从 `taskhelper.load_state()` 读取完整任务详情
- 任务卡片可点击（整个卡片），打开右侧滑入详情面板
- 面板展示：描述、task_id、分配人、状态、创建/完成时间、当前 phase、执行历史（每次 run 的耗时、结果、反馈）
- 关闭面板：点击遮罩层、按 Escape、点关闭按钮
- 面板位于 HTMX 轮询区域之外，列表刷新不影响面板状态

## Capabilities

### New Capabilities
- `task-detail-panel`: 点击任务卡片打开右侧滑入面板，展示 state.json 中的完整任务生命周期信息

### Modified Capabilities
<!-- 无 -->

## Impact

| 文件 | 变更 |
|------|------|
| `src/loop_engineering/server/api/tasks.py` | 新增 `GET /{task_id}/detail` 路由 |
| `src/loop_engineering/server/templates/base.html` | 加侧面板 CSS 样式 + `viewDetail()` / `formatDuration()` / `formatDate()` JS 函数 |
| `src/loop_engineering/server/templates/tasks.html` | 加 Alpine.js 侧面板组件 |
| `src/loop_engineering/server/templates/_tasks_items.html` | 卡片加 `onclick` + 按钮加 `event.stopPropagation()` |

不修改 `fragments.py`、`dependencies.py`、`taskhelper.py`、`task_parser.py`。
