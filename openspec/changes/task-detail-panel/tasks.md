## 1. API

- [ ] 1.1 新增 `GET /api/tasks/{task_id}/detail` 路由，调用 `taskhelper.load_state()` 返回完整 state.json

## 2. 前端基础

- [ ] 2.1 base.html 加侧面板 CSS（`.sidepanel-overlay`、`.sidepanel`、transition 类、`.detail-section`、`.run-entry`）
- [ ] 2.2 base.html 加 `viewDetail()`、`formatDuration()`、`formatDate()` JS 函数

## 3. 侧面板组件

- [ ] 3.1 tasks.html 加 Alpine.js 侧面板组件（`@open-detail.window` 触发、`x-transition` 动画、loading/error/data 状态）
- [ ] 3.2 面板内容：描述区、基本信息区（分配人/状态/创建时间/完成时间/phase）、执行历史区（每个 run 的耗时/结果/反馈）

## 4. 卡片交互

- [ ] 4.1 _tasks_items.html 卡片加 `class="task-card"` + `onclick="viewDetail(taskId)"`
- [ ] 4.2 操作按钮加 `event.stopPropagation()`（报告、重开、重置、删除）
- [ ] 4.3 CSS `.task-card` hover 效果

## 5. 验证

- [ ] 5.1 `curl GET /api/tasks/{task_id}/detail` — 200 + 完整 JSON / 404
- [ ] 5.2 浏览器验证：点击卡片 → 面板滑入 → 显示全部字段 → 点另一个任务 → 切换 → Esc/遮罩/× 关闭
- [ ] 5.3 面板打开时 HTMX 轮询刷新列表 → 面板保持不关闭
