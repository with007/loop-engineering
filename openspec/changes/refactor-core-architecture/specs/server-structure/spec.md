## ADDED Requirements

### Requirement: Server module structure
The `server/` package SHALL be structured with separate modules for pages, fragments, services, and API routers. `app.py` SHALL contain only FastAPI instance creation, router registration, and server startup.

#### Scenario: Page routes are in dedicated module
- **WHEN** a developer looks for page-level route handlers (`/`, `/tasks`, `/runs`, `/control`, `/settings`, `/setup`)
- **THEN** they find them in `server/routers/pages.py`

#### Scenario: HTMX fragments are in dedicated module
- **WHEN** a developer looks for HTMX partial-update endpoints (`/control/status-fragment`, `/tasks/list`, `/tasks/list-items`)
- **THEN** they find them in `server/routers/fragments.py`

#### Scenario: Business logic is in services layer
- **WHEN** a developer looks for tasks.md parsing or project context building logic
- **THEN** they find it in `server/services/`, not in route handlers

#### Scenario: API routers remain unchanged
- **WHEN** the restructuring is complete
- **THEN** all existing API endpoints under `/api/` continue to serve the same responses

### Requirement: SKILL_MD_TEMPLATE is an external template file
The task-runner SKILL.md template SHALL be stored as `templates/skills/task-runner/SKILL.md.j2`, rendered via Jinja2 with project-specific variables.

#### Scenario: Template file is editable independently
- **WHEN** a developer needs to modify the task-runner prompt
- **THEN** they edit `templates/skills/task-runner/SKILL.md.j2` directly, not a Python string in `setup.py`

#### Scenario: Template deployment uses deploy_skills
- **WHEN** `loop setup` runs
- **THEN** the SKILL.md.j2 template is rendered and deployed by `deploy_skills()`, consistent with other skill templates

### Requirement: Shared task filtering logic
The status filter expansion logic (e.g., "in_progress" also includes "pending_merge" and "reopen") SHALL be defined exactly once in `services/task_parser.py`.

#### Scenario: In-progress filter includes related statuses
- **WHEN** a caller requests tasks with `status=in_progress`
- **THEN** tasks with status "in_progress", "pending_merge", and "reopen" are all returned

#### Scenario: Done filter includes pending_merge
- **WHEN** a caller requests tasks with `status=done`
- **THEN** tasks with status "done" and "pending_merge" are both returned
