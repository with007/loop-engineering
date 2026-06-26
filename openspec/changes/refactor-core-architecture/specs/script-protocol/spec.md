## ADDED Requirements

### Requirement: Scripts support --format=shell
The task management scripts (`task_pick`, `task_done`, `task_cleanup`) SHALL support a `--format` parameter. `--format=shell` SHALL output `shlex.quote`-escaped shell variable assignments suitable for `eval` consumption.

#### Scenario: task_pick --format=shell outputs shell variables
- **WHEN** `task_pick with --format=shell` finds a task
- **THEN** it outputs lines like `STATUS=ok`, `TASK_ID=a1b2c3d4`, `BRANCH=agent/with/a1b2c3d4-fix-login`, `DESC=...` each on its own line

#### Scenario: task_pick --format=shell with no tasks
- **WHEN** `task_pick with --format=shell` finds no tasks
- **THEN** it outputs `STATUS=none`

#### Scenario: task_pick --format=shell with busy agent
- **WHEN** `task_pick with --format=shell` finds the agent already has an in-progress task
- **THEN** it outputs `STATUS=busy`

#### Scenario: Special characters are shell-safe
- **WHEN** a task description contains single quotes or spaces in `--format=shell` mode
- **THEN** the output is properly escaped via `shlex.quote` and safe for `eval`

### Requirement: Default format remains unchanged
When `--format` is not specified, scripts SHALL output in the existing space-separated `key=value` format for backward compatibility.

#### Scenario: task_pick without --format uses legacy output
- **WHEN** `task_pick with` is called without `--format`
- **THEN** it outputs `taskID=xxx branch=xxx desc=xxx openSpec=true|false reopen=true|false`

### Requirement: SKILL.md uses --format=shell
The task-runner SKILL.md template SHALL instruct the LLM to call scripts with `--format=shell` and consume output via `eval`.

#### Scenario: SKILL.md step 1 uses eval
- **WHEN** the task-runner executes Step 1 (task selection)
- **THEN** it calls `eval $(python -m loop_engineering.scripts.task_pick $whoami --format=shell)` and references `$TASK_ID`, `$BRANCH`, `$DESC`
