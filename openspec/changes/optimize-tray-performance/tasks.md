## 1. 事件循环控制流优化

- [ ] 1.1 将 `new_events` 中的无条件 `set_control_flow(Poll)` 移除，改为在 `StartCause::Init` 时设置 `WaitUntil`
- [ ] 1.2 在 `open_settings_window` 中切换为 `Poll` 模式（窗口需要即时渲染）
- [ ] 1.3 在 `hide_settings_window` 中恢复 `WaitUntil` 模式
- [ ] 1.4 添加 `App.last_new_events_time` 字段记录上一次 `new_events` 时间戳

## 2. rebuild_menu 状态变更检查

- [ ] 2.1 在 `update_loop_state` 中添加 `running`/`paused` 变更检测，仅在状态实际改变时调用 `rebuild_menu`
- [ ] 2.2 状态变更时添加日志 "update_loop_state: state changed running=X paused=Y"

## 3. new_events 每帧开销优化

- [ ] 3.1 `test_mode` 分支加提前短路：将测试模式相关逻辑包裹在 `if self.test_mode { ... }` 中
- [ ] 3.2 `request_redraw` 调用添加 16ms 间隔检查（`last_redraw_request` 字段），避免高频无效重绘请求

## 4. 事件循环间隔诊断日志

- [ ] 4.1 在 `new_events` 中添加 `last_new_events_time` 差值计算，间隔 ≥ 50ms 时输出 "new_events: gap=Nms"

## 5. 编译与自动化测试

- [ ] 5.1 `cargo build --release -p loop-dashboard` 确保 0 error
- [ ] 5.2 启动 exe，读日志验证：空闲时 heartbeat 间隔 ≈ 200ms（非之前的 ~0ms），CPU 占用 < 1%
- [ ] 5.3 右键托盘验证菜单正常弹出，交互正常
- [ ] 5.4 打开/关闭 settings 面板验证窗口正常渲染和关闭
