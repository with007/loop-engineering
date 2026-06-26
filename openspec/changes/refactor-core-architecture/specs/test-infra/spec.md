## ADDED Requirements

### Requirement: pytest is a project dependency
The project SHALL declare `pytest>=7.0` as a test dependency in `pyproject.toml` under `[project.optional-dependencies] test`.

#### Scenario: pytest installable
- **WHEN** `pip install -e ".[test]"` is run
- **THEN** pytest is installed and `python -m pytest --version` succeeds

### Requirement: Test directory structure
The project SHALL have a `tests/` directory at the repository root with test files mirroring the source module structure.

#### Scenario: tests directory exists
- **WHEN** a developer runs `python -m pytest`
- **THEN** pytest discovers and runs tests from the `tests/` directory

### Requirement: test_task_id.py covers task_id module
The test suite SHALL include `tests/test_task_id.py` covering all public functions in `task_id.py`: `generate_task_id`, `make_readable_slug`, `parse_task_id`, `extract_task_id_from_branch`, `make_branch_name`, `TaskLine.parse`, `TaskLine.format`.

#### Scenario: generate_task_id is deterministic
- **WHEN** `generate_task_id("hello")` is called twice
- **THEN** both calls return the same 8-character hex string

#### Scenario: generate_task_id different inputs differ
- **WHEN** `generate_task_id("hello")` and `generate_task_id("world")` are called
- **THEN** they return different values

#### Scenario: make_readable_slug handles Chinese
- **WHEN** `make_readable_slug("修复登录页报错")` is called
- **THEN** it preserves Chinese characters and does not produce empty output

#### Scenario: make_readable_slug strips invalid chars
- **WHEN** `make_readable_slug("fix [bug] {test}")` is called
- **THEN** the result does not contain `[`, `]`, `{`, or `}`

#### Scenario: make_readable_slug empty falls back
- **WHEN** `make_readable_slug("[:]{}")` is called
- **THEN** it returns a non-empty fallback like "task"

#### Scenario: parse_task_id extracts hex
- **WHEN** `parse_task_id("- [ ] desc [a1b2c3d4]")` is called
- **THEN** it returns `"a1b2c3d4"`

#### Scenario: parse_task_id returns None when absent
- **WHEN** `parse_task_id("- [ ] desc")` is called
- **THEN** it returns `None`

#### Scenario: TaskLine round-trip preserves all fields
- **WHEN** a TaskLine with all fields is formatted and re-parsed
- **THEN** all field values match the original

### Requirement: VERIFY.md pytest line is functional
The existing VERIFY.md line `python -m pytest || echo "SKIPPED: no test framework configured"` SHALL execute actual tests once pytest is configured.

#### Scenario: pytest runs without SKIPPED
- **WHEN** `python -m pytest` is run after tests are added
- **THEN** it executes tests and does not print "SKIPPED"
