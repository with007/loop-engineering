## ADDED Requirements

### Requirement: TaskLine parses tasks.md lines
The system SHALL provide a `TaskLine` class in `task_id.py` that parses a tasks.md line into structured fields and serializes back to the canonical format. `TaskLine.parse(line)` SHALL return `None` for non-task lines.

#### Scenario: Parse pending task with all fields
- **WHEN** `TaskLine.parse("- [ ] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS")` is called
- **THEN** it returns a TaskLine with status=" ", description="Fix login", assignee="with", task_id="a1b2c3d4", meta="14:30 IMP1 VFY1 PASS"

#### Scenario: Parse minimal task line
- **WHEN** `TaskLine.parse("- [ ] Fix login")` is called
- **THEN** it returns a TaskLine with status=" ", description="Fix login", assignee="", task_id="", meta=""

#### Scenario: Parse in-progress task
- **WHEN** `TaskLine.parse("- [~] Fix login (→ with) [a1b2c3d4]")` is called
- **THEN** status is "~"

#### Scenario: Parse done task with meta
- **WHEN** `TaskLine.parse("- [x] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS")` is called
- **THEN** status is "x" and meta is "14:30 IMP1 VFY1 PASS"

#### Scenario: Parse reopen task
- **WHEN** `TaskLine.parse("- [r] Fix login (→ with) [a1b2c3d4] — 14:30 IMP1 VFY1 PASS · 15:00 IMP2 VFY1 PASS")` is called
- **THEN** status is "r"

#### Scenario: Non-task line returns None
- **WHEN** `TaskLine.parse("# Tasks")` is called
- **THEN** it returns `None`

#### Scenario: Chinese description preserved
- **WHEN** `TaskLine.parse("- [ ] 修复登录页报错 (→ with) [a1b2c3d4]")` is called
- **THEN** description is "修复登录页报错"

### Requirement: TaskLine format is round-trip safe
`TaskLine.format()` SHALL produce output that `TaskLine.parse()` can re-parse to an equivalent TaskLine.

#### Scenario: Round-trip with all fields
- **WHEN** a TaskLine with all fields populated is formatted and then parsed
- **THEN** the parsed TaskLine has identical field values

#### Scenario: Round-trip with minimal fields
- **WHEN** a TaskLine with only status and description is formatted and then parsed
- **THEN** the parsed TaskLine has identical status and description, and empty optional fields

### Requirement: Tasks.md consumers use TaskLine
All code that reads or writes tasks.md lines SHALL use `TaskLine.parse()` and `TaskLine.format()` instead of inline regex.

#### Scenario: app.py _read_tasks uses TaskLine
- **WHEN** `_read_tasks()` parses tasks.md
- **THEN** it uses `TaskLine.parse(line)` internally

#### Scenario: api/tasks.py list_tasks uses TaskLine
- **WHEN** `list_tasks()` parses tasks.md
- **THEN** it uses `TaskLine.parse(line)` internally

#### Scenario: task_pick.py uses TaskLine
- **WHEN** `task_pick.py` searches for assigned tasks
- **THEN** it uses `TaskLine.parse(line)` and checks the `assignee` field

#### Scenario: task_done.py uses TaskLine
- **WHEN** `task_done.py` updates task status
- **THEN** it uses `TaskLine.parse(line)`, modifies status/meta, and calls `task.format()`

### Requirement: API task add generates task_id
The `/api/tasks/add` endpoint SHALL generate a `[task_id]` for new tasks, matching the behavior of `/tasks/add`.

#### Scenario: API add task includes task_id
- **WHEN** a task is added via `POST /api/tasks/add`
- **THEN** the written line in tasks.md includes a `[a-f0-9]{8}` task_id
