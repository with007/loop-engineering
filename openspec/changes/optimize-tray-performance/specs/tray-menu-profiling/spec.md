## ADDED Requirements

### Requirement: 记录 new_events 调用间隔
事件循环 SHALL 记录相邻 `new_events` 调用的时间戳差值，并在间隔异常时输出日志，以辅助诊断事件循环调度延迟。

#### Scenario: 正常间隔不输出
- **WHEN** 相邻 `new_events` 调用间隔 < 50ms
- **THEN** 日志 SHALL NOT 输出间隔信息（避免刷屏）

#### Scenario: 异常间隔输出日志
- **WHEN** 相邻 `new_events` 调用间隔 ≥ 50ms
- **THEN** 日志 SHALL 输出 "new_events: gap=<N>ms"，其中 N 为实际间隔毫秒数

#### Scenario: WaitUntil 模式下间隔可预测
- **WHEN** 事件循环处于 `WaitUntil` 模式且无用户交互
- **THEN** 日志中的 gap 值 SHALL 在 [180, 250]ms 范围内（对应 200ms 超时 ± 系统定时器精度）
