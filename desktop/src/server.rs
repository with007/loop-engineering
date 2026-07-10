// Python uvicorn server management
use std::net::TcpStream;
use std::process::{Child, Command};
use std::time::Duration;

#[cfg(windows)]
mod job_object {
    use windows::Win32::Foundation::HANDLE;
    use windows::Win32::System::JobObjects::*;
    use windows::Win32::System::Threading::*;

    /// A Windows Job Object that terminates child processes when the handle is closed.
    /// Uses JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE — when this handle is closed (whether
    /// by Drop or by process termination), Windows automatically kills all processes
    /// assigned to the job.
    pub struct JobObject {
        handle: HANDLE,
    }

    // SAFETY: HANDLE (kernel handle) is safe to send and share across threads.
    // Windows kernel objects are process-wide and support concurrent access.
    unsafe impl Send for JobObject {}
    unsafe impl Sync for JobObject {}

    impl JobObject {
        pub fn new() -> Option<Self> {
            unsafe {
                let handle = CreateJobObjectW(None, None).ok()?;

                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

                let size = std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>();
                SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const std::ffi::c_void,
                    size as u32,
                )
                .ok()?;

                Some(Self { handle })
            }
        }

        /// Assign a child process (by PID) to this job object so it inherits
        /// the kill-on-close behavior.
        pub fn assign_pid(&self, pid: u32) -> bool {
            unsafe {
                let proc_handle = OpenProcess(
                    PROCESS_SET_QUOTA | PROCESS_TERMINATE,
                    false,
                    pid,
                );
                match proc_handle {
                    Ok(h) => {
                        let result = AssignProcessToJobObject(self.handle, h).is_ok();
                        let _ = windows::Win32::Foundation::CloseHandle(h);
                        result
                    }
                    Err(_) => false,
                }
            }
        }
    }

    impl Drop for JobObject {
        fn drop(&mut self) {
            unsafe {
                let _ = windows::Win32::Foundation::CloseHandle(self.handle);
            }
        }
    }

    /// Kill any process listening on the given TCP port (Windows only).
    /// Uses netstat to find the PID and taskkill to terminate it.
    pub fn kill_process_on_port(port: u16) {
        let output = std::process::Command::new("cmd")
            .args(["/c", &format!("netstat -ano | findstr :{}", port)])
            .output();

        if let Ok(output) = output {
            let stdout = String::from_utf8_lossy(&output.stdout);
            for line in stdout.lines() {
                if line.contains("LISTENING") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(pid_str) = parts.last() {
                        if let Ok(pid) = pid_str.parse::<u32>() {
                            log_msg(&format!(
                                "server: killing orphan process PID {} on port {}",
                                pid, port
                            ));
                            let _ = std::process::Command::new("taskkill")
                                .args(["/F", "/PID", &pid.to_string()])
                                .stdout(std::process::Stdio::null())
                                .stderr(std::process::Stdio::null())
                                .status();
                        }
                    }
                }
            }
        }
    }

    fn log_msg(msg: &str) {
        if let Ok(exe_path) = std::env::current_exe() {
            if let Some(dir) = exe_path.parent() {
                let path = dir.join("dashboard.log");
                let ts = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default();
                let line = format!(
                    "[{}.{:03}] {}\n",
                    ts.as_secs(),
                    ts.subsec_millis(),
                    msg
                );
                let _ = std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&path)
                    .and_then(|mut f| {
                        use std::io::Write;
                        let _ = f.write_all(line.as_bytes());
                        f.flush()
                    });
            }
        }
    }
}

pub struct Server {
    child: Option<Child>,
    #[cfg(windows)]
    job: Option<job_object::JobObject>,
}

impl Server {
    pub fn new() -> Self {
        Self {
            child: None,
            #[cfg(windows)]
            job: None,
        }
    }

    /// Start the Python uvicorn server on the given port.
    ///
    /// If the port is already in use but we don't own a child handle (orphan from
    /// a previous crashed session), the orphan is killed first and a fresh process
    /// is spawned.
    pub fn start(&mut self, port: u16, python_exe: &str, app_dir: &str) -> bool {
        // ── Already running and we own the child ──────────────────────────
        // is_running() only returns true when child is Some AND alive AND port is open
        if self.is_running(port) {
            return true;
        }

        // ── Handle orphan process on port reuse ───────────────────────────
        // Port is open but we don't own a child handle → orphan from a previous
        // crashed/force-killed session. Kill it, then spawn fresh.
        if self.child.is_none() && is_port_open(port) {
            #[cfg(windows)]
            {
                job_object::kill_process_on_port(port);
                // Give the OS a moment to release the port
                std::thread::sleep(Duration::from_millis(1000));
            }
            #[cfg(not(windows))]
            {
                let _ = std::process::Command::new("fuser")
                    .args(["-k", &format!("{}/tcp", port)])
                    .output();
                std::thread::sleep(Duration::from_millis(500));
            }
        }

        // If port still occupied after orphan cleanup, fail
        if is_port_open(port) {
            return false;
        }

        // ── Clean up any dead child reference ─────────────────────────────
        if let Some(ref mut child) = self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.child = None;
        #[cfg(windows)]
        {
            self.job = None;
        }

        // ── Spawn new process ─────────────────────────────────────────────
        let mut cmd = Command::new(python_exe);
        cmd.args([
            "-c",
            &format!(
                "import uvicorn; from loop_engineering.server.app import app; uvicorn.run(app, host='127.0.0.1', port={}, log_level='warning')",
                port
            ),
        ])
        .current_dir(app_dir)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        }

        let child = cmd.spawn();

        match child {
            Ok(c) => {
                let pid = c.id();

                // ── Windows Job Object: bind child lifecycle to parent ──
                #[cfg(windows)]
                {
                    let job = job_object::JobObject::new();
                    if let Some(ref j) = job {
                        j.assign_pid(pid);
                    }
                    self.job = job;
                }

                self.child = Some(c);

                // Wait for server to be ready
                for _ in 0..20 {
                    std::thread::sleep(Duration::from_millis(500));
                    if is_port_open(port) {
                        return true;
                    }
                    // Check if process died
                    if let Some(ref mut child) = self.child {
                        match child.try_wait() {
                            Ok(Some(_)) => {
                                // Process died, log error
                                let _ = std::fs::write(
                                    std::env::current_exe()
                                        .unwrap()
                                        .parent()
                                        .unwrap()
                                        .join("dashboard.log"),
                                    "Server process exited unexpectedly\n",
                                );
                                return false;
                            }
                            _ => {}
                        }
                    }
                }
                is_port_open(port)
            }
            Err(e) => {
                let _ = std::fs::write(
                    std::env::current_exe()
                        .unwrap()
                        .parent()
                        .unwrap()
                        .join("dashboard.log"),
                    format!("Failed to start server: {}\n", e),
                );
                false
            }
        }
    }

    /// Restart the server
    pub fn restart(&mut self, port: u16, python_exe: &str, app_dir: &str) -> bool {
        self.stop();
        self.start(port, python_exe, app_dir)
    }

    /// Stop the server: kill the child process and release the job object.
    pub fn stop(&mut self) {
        if let Some(ref mut child) = self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.child = None;
        #[cfg(windows)]
        {
            self.job = None;
        }
    }

    /// Check if the server process is alive and port is open.
    /// Only returns true if we actually own the child handle.
    pub fn is_running(&mut self, port: u16) -> bool {
        if let Some(ref mut child) = self.child {
            match child.try_wait() {
                Ok(None) => return is_port_open(port),
                _ => {}
            }
        }
        // self.child is None → we don't own it, report as not running
        false
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop();
    }
}

pub fn is_port_open(port: u16) -> bool {
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{}", port).parse().unwrap(),
        Duration::from_secs(1),
    )
    .is_ok()
}

pub fn find_available_port(start: u16) -> u16 {
    for port in start..start + 20 {
        if !is_port_open(port) {
            return port;
        }
    }
    start
}
