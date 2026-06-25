## ADDED Requirements

### Requirement: Implementer receives history context on reopen
When `reopen=true`, the task-runner SHALL inject old commit report and reopen feedback into the implementer's prompt.

#### Scenario: Implementer prompt with history
- **WHEN** task-runner spawns implementer for a `reopen=true` task
- **THEN** the implementer prompt contains:
  - `## 历史报告` section with the latest commit body from the existing branch
  - `## 本轮反馈` section with feedback text from tasks.md indented lines

#### Scenario: No feedback available
- **WHEN** replay task has indented lines containing only whitespace or no indented lines
- **THEN** implementer prompt still includes `## 历史报告` but omits `## 本轮反馈`

### Requirement: Implementer includes feedback in commit
Implementer SHALL prepend a `## 本轮反馈` section to their output, containing the feedback from the reopen prompt.

#### Scenario: Commit message with feedback
- **WHEN** implementer outputs their report
- **THEN** the report includes `## 本轮反馈` as the first section (before `## 实现思路`)

### Requirement: task-runner checks out existing branch on reopen
When `reopen=true`, task-runner Step 2 SHALL execute `git checkout <BRANCH>` instead of `git checkout -B <BRANCH> master`.

#### Scenario: Reopen branch checkout
- **WHEN** task-runner processes a task with `reopen=true` and `branch=agent/with/0d3e52c8-翻译tab`
- **THEN** it runs `git checkout agent/with/0d3e52c8-翻译tab`

#### Scenario: Fresh task branch creation unchanged
- **WHEN** task-runner processes a task with `reopen=false`
- **THEN** it runs `git checkout -B <BRANCH> master` (existing behavior)
