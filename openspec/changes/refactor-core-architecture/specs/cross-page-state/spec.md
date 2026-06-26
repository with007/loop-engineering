## ADDED Requirements

### Requirement: Project state object
The frontend SHALL provide a single `Project` JavaScript object in `base.html` as the sole entry point for reading and binding the current project root to requests.

#### Scenario: Project.current reads from URL
- **WHEN** `Project.current()` is called on a page with `?project=/path/to/project`
- **THEN** it returns `/path/to/project`

#### Scenario: Project.current returns empty string when absent
- **WHEN** `Project.current()` is called on a page without `?project=` parameter
- **THEN** it returns `""`

#### Scenario: Project.bind appends project to path
- **WHEN** `Project.bind("/api/tasks/list")` is called with current project `/p`
- **THEN** it returns `/api/tasks/list?project=%2Fp`

#### Scenario: Project.bind is idempotent
- **WHEN** `Project.bind("/api/tasks/list?project=/p")` is called
- **THEN** it returns the path unchanged

### Requirement: Single HTMX configRequest listener
The frontend SHALL have exactly one `htmx:configRequest` event listener that adds the `X-Loop-Project` HTTP header to all requests.

#### Scenario: Header added to all HTMX requests
- **WHEN** any HTMX request is dispatched while `Project.current()` returns a project path
- **THEN** the request includes the `X-Loop-Project` header with the project path value

#### Scenario: Header not added when no project
- **WHEN** no project is selected (Project.current() returns "")
- **THEN** the `X-Loop-Project` header is not added

### Requirement: switchProject uses pushState before AJAX
The project switcher SHALL update `window.location` via `history.pushState` before dispatching the HTMX navigation request.

#### Scenario: pushState before htmx.ajax
- **WHEN** the user switches from project A to project B
- **THEN** `history.pushState` updates the URL to `?project=B` before `htmx.ajax` fires, ensuring the listener reads the new project value

### Requirement: Templates do not hardcode project param
HTML templates SHALL NOT include `?project={{ current_root }}` in HTMX attribute values. The project SHALL be carried exclusively by the `X-Loop-Project` header.

#### Scenario: settings.html form has no project param
- **WHEN** the settings page template is rendered
- **THEN** the `<form hx-post="...">` attribute does not contain `?project=`

#### Scenario: Alpine fetch calls use Project.current
- **WHEN** Alpine.js components make `fetch()` API calls
- **THEN** they construct the URL via `Project.bind()` or manually read `Project.current()` to set the `X-Loop-Project` header

### Requirement: Backend accepts X-Loop-Project header
The `resolve_project_root()` function SHALL read the `X-Loop-Project` HTTP header as the second-highest priority source for project root resolution (after explicit `project` parameter, before `LOOP_PROJECT_ROOT` env var).

#### Scenario: Header takes precedence over env var
- **WHEN** a request has `X-Loop-Project: /project/B` header and `LOOP_PROJECT_ROOT=/project/A`
- **THEN** `resolve_project_root()` returns `/project/B`
