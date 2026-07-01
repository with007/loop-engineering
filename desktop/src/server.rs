// Python uvicorn server management
use std::net::TcpStream;
use std::process::{Child, Command};
use std::time::Duration;

pub struct Server {
    child: Option<Child>,
}

impl Server {
    pub fn new() -> Self {
        Self { child: None }
    }

    /// Start the Python uvicorn server on the given port
    pub fn start(&mut self, port: u16, python_exe: &str, app_dir: &str) -> bool {
        if self.is_running(port) {
            return true;
        }

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
                                    std::env::current_exe().unwrap().parent().unwrap().join("dashboard.log"),
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
                    std::env::current_exe().unwrap().parent().unwrap().join("dashboard.log"),
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

    /// Stop the server
    pub fn stop(&mut self) {
        if let Some(ref mut child) = self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.child = None;
    }

    /// Check if the server process is alive and port is open
    pub fn is_running(&mut self, port: u16) -> bool {
        if let Some(ref mut child) = self.child {
            match child.try_wait() {
                Ok(None) => return is_port_open(port),
                _ => {}
            }
        }
        is_port_open(port)
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
