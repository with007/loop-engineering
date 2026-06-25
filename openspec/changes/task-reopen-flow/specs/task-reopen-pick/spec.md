## ADDED Requirements

### Requirement: task_pick matches `[r]` state
task_pick SHALL match `[r]` lines in addition to `[ ]` when selecting next task for the current user.

#### Scenario: Pick reopen task
- **WHEN** tasks.md has `- [r] 翻译tab (→ withg) [0d3e52c8]`
- **THEN** task_pick outputs `taskID=0d3e52c8 reopen=true branch=<existing-branch> desc=翻译tab`

### Requirement: task_pick discovers existing branch for reopen
For `[r]` tasks, task_pick SHALL query git branches matching `agent/{whoami}/{task_id}-*` and output the most recent branch name.

#### Scenario: Branch found
- **WHEN** `git branch -a --list "agent/with/0d3e52c8-*" --sort=-committerdate` returns `agent/with/0d3e52c8-翻译tab`
- **THEN** task_pick outputs `branch=agent/with/0d3e52c8-翻译tab`

#### Scenario: No branch found (degraded)
- **WHEN** no branch matches `agent/with/0d3e52c8-*`
- **THEN** task_pick generates a new branch name via `make_branch_name` and outputs `reopen=false` (treating it as a fresh task)

#### Scenario: Multiple branches, pick latest
- **WHEN** both `agent/with/0d3e52c8-v1` and `agent/with/0d3e52c8-v2` exist
- **THEN** task_pick outputs the branch with most recent commit date

### Requirement: task_pick output includes reopen flag
The task_pick output format SHALL include `reopen=true` or `reopen=false` based on task state.

#### Scenario: Reopen task output format
- **WHEN** task_pick selects a `[r]` task
- **THEN** output includes `reopen=true` as an additional field
