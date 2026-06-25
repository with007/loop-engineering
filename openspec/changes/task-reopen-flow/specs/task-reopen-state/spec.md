## ADDED Requirements

### Requirement: Tasks.md supports `[r]` state
The tasks.md parser SHALL recognize `[r]` as a valid task state, semantically equivalent to pending (`[ ]`) for task-runner pickup but indicating the task was previously completed and reopened.

#### Scenario: Parse reopen task
- **WHEN** tasks.md contains `- [r] 翻译tab页标题为中文 (→ withg) [0d3e52c8] — IMP1 VFY1 PASS`
- **THEN** the task list API returns status `reopen` for this task

#### Scenario: Reopen task visible in task list
- **WHEN** task list is rendered
- **THEN** `[r]` tasks display with a distinct badge ("需返工") and color, separate from pending/in-progress/done

### Requirement: Reopen state flows back to done
After task-runner completes a `[r]` task, the state SHALL return to `[x]` with `IMPx VFYx PASS` appended to the history.

#### Scenario: Reopen task completion
- **WHEN** task_done processes a `[r]` task with result PASS
- **THEN** tasks.md line changes from `[r]` to `[x]` and meta appends new IMP/VFY record (e.g., `IMP1 VFY1 PASS · IMP2 VFY1 PASS`)

### Requirement: Reopen feedback via indented lines
`[r]` task lines MAY have indented continuation lines that contain user feedback for the implementer.

#### Scenario: Parse feedback lines
- **WHEN** tasks.md contains:
  ```
  - [r] 翻译tab (→ withg) [0d3e52c8] — IMP1 VFY1 PASS
    上次漏了英文环境回退
    日文也不行
  ```
- **THEN** the feedback text "上次漏了英文环境回退\n日文也不行" is extractable for implementer context

#### Scenario: Feedback lines survive task completion
- **WHEN** task_done changes `[r]` to `[x]`
- **THEN** feedback indented lines remain in tasks.md unchanged

### Requirement: Reopen API endpoint
The system SHALL provide `PUT /api/tasks/{task_id}/reopen` that transitions a `[x]` task to `[r]` with optional description update and feedback lines.

#### Scenario: Reopen with feedback
- **WHEN** PUT /api/tasks/0d3e52c8/reopen with body `{"feedback": "漏了英文回退\n日文也不行"}`
- **THEN** the task status changes from `[x]` to `[r]` and two indented feedback lines are added below it

#### Scenario: Reopen non-existent task
- **WHEN** PUT /api/tasks/nonexist/reopen
- **THEN** returns 404

#### Scenario: Reopen already pending task
- **WHEN** PUT /api/tasks/xxx/reopen on a `[ ]` or `[~]` task
- **THEN** returns 400 with message "Only completed tasks can be reopened"
