## ADDED Requirements

### Requirement: Report API returns all rounds
`GET /api/tasks/{task_id}/report` SHALL return all commits matching the task ID, ordered by date descending.

#### Scenario: Multiple reports for same task
- **WHEN** task `0d3e52c8` has two commits in git history matching `[0d3e52c8]`
- **THEN** the API returns `{"reports": [{commit_hash, date, imp_round, body}, ...]}` with both commits

#### Scenario: Single report
- **WHEN** task has one matching commit
- **THEN** the API returns `{"reports": [...]}` with one entry

#### Scenario: No reports
- **WHEN** no commit matches the task ID
- **THEN** the API returns 404

### Requirement: Report modal supports round switching
The report modal SHALL display a tab for each report round, defaulting to the latest.

#### Scenario: Multi-round report viewer
- **WHEN** user opens report for a task with 2 rounds
- **THEN** modal shows tabs `[IMP1]` `[IMP2]` with IMP2 selected, and the body of IMP2 rendered as markdown
- **THEN** clicking IMP1 switches to that round's report

#### Scenario: Single round
- **WHEN** a task has one round
- **THEN** modal shows no tabs, directly renders the report body

### Requirement: Frontend reopen button and modal
Completed (`[x]`) task cards SHALL show a "重新打开" button that opens a modal allowing the user to edit the task description and provide feedback.

#### Scenario: Reopen button visibility
- **WHEN** task list renders a task with status `done` or `pending_merge`
- **THEN** a "重新打开" button is visible alongside the "查看报告" button

#### Scenario: Reopen modal submission
- **WHEN** user fills feedback and clicks "重新打开" in the modal
- **THEN** `PUT /api/tasks/{task_id}/reopen` is called, and the task list refreshes showing the task as `[r]`
