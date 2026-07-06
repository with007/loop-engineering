## ADDED Requirements

### Requirement: 菜单仅在状态变更时重建
`rebuild_menu` SHALL 仅在 `running` 或 `paused` 状态实际变化时被调用，不再跟随每次 poll 结果无条件执行。

#### Scenario: 状态不变时不重建
- **WHEN** poll 返回的 `running` 和 `paused` 与当前 `AppState` 中的值完全一致
- **THEN** `rebuild_menu` SHALL NOT 被调用

#### Scenario: running 状态变更时重建
- **WHEN** poll 返回 `running: true` 而当前 `AppState.loop_running` 为 `false`
- **THEN** `rebuild_menu(true, paused)` SHALL 被调用一次

#### Scenario: paused 状态变更时重建
- **WHEN** poll 返回 `paused: true` 而当前 `AppState.loop_paused` 为 `false`
- **THEN** `rebuild_menu(true, true)` SHALL 被调用一次

#### Scenario: 状态变更日志记录
- **WHEN** `rebuild_menu` 因状态变更被触发
- **THEN** 日志 SHALL 输出 "update_loop_state: state changed running=<bool> paused=<bool>"
