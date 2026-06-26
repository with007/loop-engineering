## ADDED Requirements

### Requirement: Centralized project root resolution
The system SHALL provide `find_project_root()` and `resolve_project_root()` in `path_utils.py` as the single source for project root directory resolution, replacing all private `_project_root` and `_find_project_root` implementations.

#### Scenario: find_project_root searches upward
- **WHEN** `find_project_root()` is called from any subdirectory of a loop-engineering project
- **THEN** it returns the directory containing `.loop-engineering/loop-config.yaml`

#### Scenario: find_project_root fallback to cwd
- **WHEN** `find_project_root()` is called outside any loop-engineering project
- **THEN** it returns the current working directory

#### Scenario: resolve_project_root uses explicit project first
- **WHEN** `resolve_project_root(project="/path/to/project")` is called
- **THEN** it returns `/path/to/project` regardless of env vars or cwd

#### Scenario: resolve_project_root uses header second
- **WHEN** `resolve_project_root()` is called with an `X-Loop-Project` HTTP header present
- **THEN** it returns the header value before falling back to env var

#### Scenario: resolve_project_root uses env var third
- **WHEN** `resolve_project_root()` is called without explicit project or header, but `LOOP_PROJECT_ROOT` is set
- **THEN** it returns `LOOP_PROJECT_ROOT`

#### Scenario: resolve_project_root uses cwd search last
- **WHEN** `resolve_project_root()` is called without project, header, or env var
- **THEN** it calls `find_project_root()` for the fallback

### Requirement: Centralized default branch detection
The system SHALL provide `get_default_branch(repo_path)` in `path_utils.py` as the single source for default branch detection.

#### Scenario: Local master preferred
- **WHEN** `get_default_branch()` is called and local `master` branch exists
- **THEN** it returns `"master"`

#### Scenario: Local main as fallback
- **WHEN** local `master` does not exist but `main` does
- **THEN** it returns `"main"`

#### Scenario: Remote refs as last resort
- **WHEN** neither local `master` nor `main` exist
- **THEN** it checks `origin/master` then `origin/main` and returns the first available

### Requirement: Centralized agent directory computation
The system SHALL provide `get_agent_dir(config)` and `get_data_agent_dir(config)` in `config.py` as the single source for agent worktree path computation.

#### Scenario: get_agent_dir computes from config
- **WHEN** config has `agent.workspace = "/ws"` and `project.name = "myproject"`
- **THEN** `get_agent_dir(config)` returns `"/ws/myproject"`

#### Scenario: get_data_agent_dir returns None when absent
- **WHEN** config has no `data_repo`
- **THEN** `get_data_agent_dir(config)` returns `None`
