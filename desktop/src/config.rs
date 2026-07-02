// Config file management
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Config {
    #[serde(default = "default_port")]
    pub port: u16,
    #[serde(default = "default_autostart")]
    pub autostart: bool,
    #[serde(default = "default_auto_open_browser")]
    pub auto_open_browser: bool,
}

fn default_port() -> u16 { 8765 }
fn default_autostart() -> bool { true }
fn default_auto_open_browser() -> bool { true }

impl Default for Config {
    fn default() -> Self {
        Self { port: 8765, autostart: true, auto_open_browser: true }
    }
}

impl Config {
    pub fn load(exe_dir: &PathBuf) -> Self {
        let path = exe_dir.join("dashboard-settings.json");
        if let Ok(data) = std::fs::read_to_string(&path) {
            serde_json::from_str(&data).unwrap_or_default()
        } else {
            let cfg = Config::default();
            cfg.save(exe_dir);
            cfg
        }
    }

    pub fn save(&self, exe_dir: &PathBuf) {
        let path = exe_dir.join("dashboard-settings.json");
        if let Ok(data) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(&path, data);
        }
    }
}
