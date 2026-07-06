## Why

桌面端 Loop Dashboard 的事件循环使用 `ControlFlow::Poll` 持续空转，导致空闲 CPU 占用高达一个完整核心（~100%）。同时 `rebuild_menu` 在每次 server poll（10s 间隔）时无条件重建菜单，即使状态未发生变化。这两个问题叠加导致：(1) 不必要的功耗和 CPU 资源消耗，(2) Poll 循环与 `TrackPopupMenu` 的模态消息循环竞争可能加剧菜单弹出延迟。当前代码没有菜单弹出计时代码，无法建立性能基准线。

## What Changes

- 将事件循环从 `ControlFlow::Poll` 改为 `ControlFlow::WaitUntil`，空闲时 sleep 到下一次 poll，窗口打开时恢复 Poll 模式以保证即时渲染
- `rebuild_menu` 加入状态变更检查（dirty check），仅在 `running` / `paused` 状态真正改变时才重建菜单
- 减少 `new_events` 每帧开销：`set_control_flow` 仅在模式切换时调用、`test_mode` 分支提前短路
- 在托盘右键响应路径加入计时代码，日志记录从 `WM_RBUTTONDOWN` 到菜单出现的时间间隔
- **BREAKING**: 无

## Capabilities

### New Capabilities
- `tray-event-loop`: 空闲 CPU < 1%，通过 `WaitUntil` 替代 `Poll` 实现，窗口打开时自动恢复即时渲染
- `tray-menu-rebuild`: 菜单重建仅在 loop 状态（running/paused）实际变更时触发，不再跟随 10s poll 无条件重建
- `tray-menu-profiling`: 日志记录菜单弹出延迟基准线数据，为后续优化提供可量化依据

### Modified Capabilities
<!-- 本次不修改任何已有 spec -->

## Impact

- **Affected code**: `desktop/src/main.rs` — `App::new_events()`, `App::update_loop_state()`, `App::window_event()` 控制流逻辑
- **Dependencies**: 无新增依赖；考虑后续升级 `tray-icon` 0.19 → 0.21（非本次范围）
- **Behavior**: 托盘图标、菜单交互、设置面板行为不变；仅改变事件循环调度策略
- **Risk**: `WaitUntil` 的超时设置需要平衡 CPU 节省和 poll 延迟；菜单弹出自带模态循环不受影响
