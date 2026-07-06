## Context

Loop Dashboard 桌面端使用 winit + glutin + egui_glow 构建。应用以系统托盘（tray icon）形态常驻后台，无可见窗口时事件循环仍持续运行。当前实现：

- `ControlFlow::Poll` — 无论是否有事件，事件循环每个 tick 空转
- `new_events()` 每次迭代执行心跳检查、settings 窗口重绘请求、test mode 检查、server 状态 poll
- `update_loop_state()` 被 poll 结果触发时无条件调用 `rebuild_menu()`，重建所有项目子菜单
- 菜单弹出由 `tray-icon` crate（v0.19）内部的 Win32 `TrackPopupMenu` 处理，该调用进入独立模态消息循环

性能目标：空闲 CPU < 1%，右键菜单弹出 < 100ms，日志帧间隔 < 16ms。

## Goals / Non-Goals

**Goals:**
- 空闲时（无窗口、无用户交互）事件循环 sleep 而非空转，CPU 降至 < 1%
- 菜单重建仅在 loop 状态（running / paused）实际变更时执行
- 减少 `new_events` 每次 tick 的无效操作
- 加入菜单弹出计时代码，日志可量化延迟

**Non-Goals:**
- 升级 `tray-icon` 版本（0.19 → 0.21）——API 有变，留待后续
- 优化 `rebuild_menu` 内部的内存分配模式——当前项目数 ≤ 10，开销可忽略
- 优化 Python server 侧性能——本 change 仅涉及 Rust 桌面端事件循环
- 优化 egui 渲染性能——仅在窗口打开时可接受当前帧率

## Decisions

### Decision 1: 空闲时用 `WaitUntil` 替代 `Poll`

**选择**: `ControlFlow::Poll` → `ControlFlow::WaitUntil(Instant::now() + Duration::from_millis(200))`

**理由**:
- `WaitUntil` 让 winit 在超时前 sleep，依赖 OS 定时器唤醒，不消耗 CPU
- 200ms 超时保证 heartbeat（2s）和 poll（10s）仍能在合理精度内触发
- winit 在收到新事件（如托盘右键、重绘请求）时会自动提前唤醒，不影响交互响应

**替代方案**:
- `ControlFlow::Wait` — 完全靠事件唤醒，但后台 worker 线程的 `PollResult` 通过 `EventLoopProxy` 发送，会被 winit 当作自定义事件处理，`Wait` 也能响应。但 `Wait` 的风险在于：如果 proxy 在某些 winit 实现中没有正确唤醒 Wait，poll 永远不触发。`WaitUntil` 有硬超时兜底，更加安全。
- 保持 `Poll` + `std::thread::sleep` — 不可行，winit 的 Poll 模式不给我们插入 sleep 的位置。

**窗口打开时的行为**: settings 窗口打开时恢复 `Poll` 模式，确保 egui 渲染帧率。窗口关闭后切回 `WaitUntil`。

### Decision 2: `rebuild_menu` 加 dirty check

**选择**: 在 `update_loop_state` 中比较新旧状态，仅在 `running` 或 `paused` 变化时调用 `rebuild_menu`。

```rust
// Before:
fn update_loop_state(&mut self, running: bool, paused: bool) {
    let mut s = self.state.lock().unwrap();
    s.loop_running = running;
    s.loop_paused = paused;
    drop(s);
    self.rebuild_menu(running, paused);  // always
}

// After:
fn update_loop_state(&mut self, running: bool, paused: bool) {
    let changed = {
        let mut s = self.state.lock().unwrap();
        let changed = s.loop_running != running || s.loop_paused != paused;
        s.loop_running = running;
        s.loop_paused = paused;
        changed
    };
    if changed {
        log!("update_loop_state: state changed running={} paused={}", running, paused);
        self.rebuild_menu(running, paused);
    }
}
```

**理由**: 每 10s 的 poll 绝大多数时候状态不变，避免无谓的 Vec clear/push + Menu 构造。

### Decision 3: `new_events` 减负

**具体改动**:

1. `event_loop.set_control_flow()` 仅在模式切换时调用，而非每个 tick：
   - `StartCause::Init` 时设置初始模式
   - 窗口打开/关闭时切换 Poll ↔ WaitUntil
   - 移除 `new_events` 中的无条件 `set_control_flow(Poll)`

2. `test_mode` 检查提到函数开头，用一个 `if self.test_mode` 包裹所有 test 逻辑，生产环境一次布尔判断跳过。

3. `request_redraw` 不做额外调整——窗口打开时 egui 本身已经在 `on_window_event` 中通过 `event_response.repaint` 控制重绘，`new_events` 中的 `request_redraw` 将保留但降低频率到每 16ms 一次（加 `last_redraw_request` 时间戳检查）。

### Decision 4: 菜单弹出计时代码

**选择**: 不在 Rust 端加计时代码，因为 `TrackPopupMenu` 是 `tray-icon` crate 内部调用的，我们无法在调用前后插入计时代码而不 fork/modify crate。

**替代方案**: 在 `new_events` 中检测 poll 间隔变化。当 `TrackPopupMenu` 进入模态循环时，winit 的 Poll 回调频率会显著下降（因为消息泵被菜单接管）。通过两次 `new_events` 调用的间隔推断菜单弹出时间：
- 正常 Poll 间隔：~0-1ms（高速空转）
- 菜单打开时：Poll 回调暂停，下一次回调间隔显著 > 16ms
- 菜单关闭后：Poll 恢复，记录间隔

实际上，这项测量对于 `WaitUntil` 方案意义有限——`WaitUntil` 本身就有 sleep 间隔。因此计时代码定位为：用 `last_new_events_time` 记录相邻 `new_events` 时间戳差值，日志中输出异常间隔（> 50ms），以观察菜单弹出/交互延迟模式。

## Risks / Trade-offs

- **[Risk] `WaitUntil` 超时设置不当导致 poll 延迟过大** → 200ms 超时保证最坏情况下 poll 精度在 200ms 内，实际唤醒通常由事件驱动更早。10s poll 周期对 200ms 误差不敏感。
- **[Risk] 某些 Windows 版本上 `WaitUntil` 唤醒不可靠** → 200ms 硬超时兜底，即使事件唤醒机制有问题，最多 200ms 后也会检查。
- **[Risk] 窗口打开/关闭切换控制流时出现竞态** → 切 Poll 的时机在 `open_settings_window` 和 `hide_settings_window` 中，这两个函数都在主线程事件回调中执行，无线程安全风险。
- **[Trade-off] 不升级 tray-icon 版本** → 已知 v0.19 的菜单实现有性能提升空间，但 API 变化（从 `Menu::with_items` 到新 API）风险大于收益。留待单独的 change。
