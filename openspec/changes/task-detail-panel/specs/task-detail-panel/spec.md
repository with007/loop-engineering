## ADDED Requirements

### Requirement: Click task card to open detail panel

The system SHALL open a side panel when the user clicks a task card. The panel SHALL slide in from the right edge of the viewport with a 250ms ease-out transition.

#### Scenario: Open panel from task card
- **WHEN** user clicks anywhere on a task card
- **THEN** a side panel slides in from the right showing the task's detail information

#### Scenario: Close panel via overlay click
- **WHEN** user clicks the overlay area outside the side panel
- **THEN** the panel closes with a 200ms ease-in transition

#### Scenario: Close panel via Escape key
- **WHEN** user presses the Escape key
- **THEN** the panel closes

#### Scenario: Close panel via close button
- **WHEN** user clicks the (×) button in the panel header
- **THEN** the panel closes

#### Scenario: Switch between tasks
- **WHEN** user clicks a different task card while the panel is open
- **THEN** the panel updates to show the newly selected task's information without closing and reopening

### Requirement: Action buttons do not open panel

The system SHALL prevent action button clicks (report, reopen, reset, delete) from triggering the detail panel.

#### Scenario: Click report button
- **WHEN** user clicks the report button on a task card
- **THEN** the report modal opens and the detail panel does NOT open

#### Scenario: Click delete button
- **WHEN** user clicks the delete button on a task card
- **THEN** the delete confirmation triggers and the detail panel does NOT open

### Requirement: Detail panel shows task metadata

The system SHALL display the following information from state.json in the detail panel: description, task_id, assignee, status (as colored badge), created_at, completed_at (last run), current phase, and run history.

#### Scenario: View completed task
- **WHEN** user opens a completed task's detail panel
- **THEN** the panel shows description, task_id, assignee, "已完成" status badge, creation date, and completion date

#### Scenario: View task with execution history
- **WHEN** user opens a task that has multiple runs
- **THEN** the panel shows each run with: run number, result (PASS/FAIL badge), start time, end time, computed duration, IMP/VFY round range, and user feedback if present

#### Scenario: View task with no runs
- **WHEN** user opens a task that has no execution history
- **THEN** the panel shows "尚无执行记录"

#### Scenario: View task with active phase
- **WHEN** user opens a task that has a current phase (e.g., "IMP:agent:branch:2")
- **THEN** the panel displays the phase string highlighted

### Requirement: Panel survives HTMX polling

The system SHALL place the detail panel outside HTMX polling regions so that page refreshes do not close or reset the panel.

#### Scenario: Panel stays open during list refresh
- **WHEN** the task list refreshes via HTMX polling while the detail panel is open
- **THEN** the panel remains open and continues showing the same task

### Requirement: API endpoint returns task detail

The system SHALL provide `GET /api/tasks/{task_id}/detail` that returns the full state.json content for a given task.

#### Scenario: Fetch existing task detail
- **WHEN** client requests `/api/tasks/{task_id}/detail` for a task with state.json
- **THEN** the API returns 200 with the complete state.json object

#### Scenario: Fetch nonexistent task
- **WHEN** client requests `/api/tasks/{task_id}/detail` for a nonexistent task_id
- **THEN** the API returns 404
