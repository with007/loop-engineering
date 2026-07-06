## ADDED Requirements

### Requirement: 空闲时事件循环使用 WaitUntil
事件循环在无可见窗口时 SHALL 使用 `ControlFlow::WaitUntil` 替代 `ControlFlow::Poll`，使得空闲时 CPU 占用 < 1%。

#### Scenario: 启动后无窗口进入 WaitUntil
- **WHEN** 应用启动完毕、tray icon 创建完成、无 settings 窗口
- **THEN** 事件循环 SHALL 设置为 `ControlFlow::WaitUntil` 模式，超时间隔 ≤ 200ms

#### Scenario: settings 窗口打开时切换为 Poll
- **WHEN** 用户打开 settings 窗口（通过托盘菜单或首次运行自动打开）
- **THEN** 事件循环 SHALL 切换为 `ControlFlow::Poll` 模式以保证 egui 即时渲染

#### Scenario: settings 窗口关闭后恢复 WaitUntil
- **WHEN** settings 窗口被关闭（点击 X 或保存/取消）
- **THEN** 事件循环 SHALL 恢复为 `ControlFlow::WaitUntil` 模式

#### Scenario: 空闲 CPU 占用 < 1%
- **WHEN** 应用启动 30 秒后、无 settings 窗口、无用户交互
- **THEN** 进程 CPU 占用率 SHALL 稳定在 1% 以下（通过任务管理器或 `GetProcessTimes` 测量）

### Requirement: 后台 poll 不受 WaitUntil 影响
Server 状态 poll（10s 间隔）SHALL 在 `WaitUntil` 模式下正常触发，精度不受影响。

#### Scenario: Poll 在 WaitUntil 模式下正常执行
- **WHEN** 事件循环处于 `WaitUntil` 模式
- **THEN** 每 10 秒 SHALL 触发一次 server 状态 poll，日志输出 "polling server status..."
