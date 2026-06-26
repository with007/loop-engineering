## ADDED Requirements

### Requirement: atomic_write function
The system SHALL provide an `atomic_write(path, content)` function in `utils.py` that writes file content atomically using `tempfile.mkstemp` + `os.replace`.

#### Scenario: Partial write is never visible
- **WHEN** a process is killed mid-way through `atomic_write()`
- **THEN** the target file either contains the old complete content or does not exist yet; partial content is never visible

#### Scenario: Successful write replaces target
- **WHEN** `atomic_write()` completes successfully
- **THEN** the target file contains the complete new content

### Requirement: Config writes use atomic_write
All YAML and JSON configuration file writes SHALL use `atomic_write()` instead of direct `open().write()`.

#### Scenario: loop-config.yaml uses atomic write
- **WHEN** `write_config()` saves the project configuration
- **THEN** it uses `atomic_write()` internally

#### Scenario: .mcp.json uses atomic write
- **WHEN** `_write_json_if_changed()` writes MCP configuration
- **THEN** it uses `atomic_write()` internally

#### Scenario: Run log JSON uses atomic write
- **WHEN** `write_run_log()` saves a run log entry
- **THEN** it uses `atomic_write()` internally

### Requirement: Signal files excluded
Control signal files (heartbeat, pause, throttle, pid) SHALL continue using direct `open().write()` without atomic write.

#### Scenario: Heartbeat still uses direct write
- **WHEN** `write_heartbeat()` is called
- **THEN** it uses the existing `open().write()` pattern, not `atomic_write()`
