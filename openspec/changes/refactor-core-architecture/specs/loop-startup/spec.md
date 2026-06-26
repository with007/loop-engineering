## ADDED Requirements

### Requirement: Heartbeat loop managed by Python
The `start_loop()` function in `control.py` SHALL manage the heartbeat write loop in Python after launching the terminal window process. The PowerShell script SHALL be reduced to terminal window startup and SendKeys only.

#### Scenario: Python writes heartbeat after process start
- **WHEN** `start_loop()` successfully launches the terminal process
- **THEN** Python enters a loop that calls `write_heartbeat()` every 30 seconds while `proc.poll() is None`

#### Scenario: Python cleans up heartbeat on exit
- **WHEN** the terminal process exits
- **THEN** Python removes the heartbeat file

#### Scenario: PowerShell script has no heartbeat loop
- **WHEN** the generated `loop.ps1` is inspected
- **THEN** it contains terminal startup and SendKeys logic, but no heartbeat `while` loop

### Requirement: PowerShell script handles startup only
The PowerShell script SHALL be responsible for: launching the CMD terminal window, capturing the PID, and sending the `/runloop` keystroke sequence via SendKeys.

#### Scenario: PID captured correctly
- **WHEN** the PowerShell script starts the CMD process
- **THEN** it writes the CMD process PID to `loop.pid` before exiting

#### Scenario: SendKeys sends /runloop
- **WHEN** the terminal window is active
- **THEN** SendKeys types `/runloop` followed by Enter

### Requirement: start_loop returns only after process launched
The `start_loop()` function SHALL return immediately after launching the terminal process and entering the heartbeat loop (in a background thread or non-blocking).

#### Scenario: Dashboard remains responsive
- **WHEN** `start_loop()` is called from the API endpoint
- **THEN** the HTTP response is returned promptly, and the heartbeat loop runs in background
