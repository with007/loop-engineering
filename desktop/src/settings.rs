// Settings dialog — now handled inline in main.rs via egui Window
pub fn show_settings_dialog(_exe_dir: std::path::PathBuf, _current_port: u16, _current_autostart: bool) {
    // No-op: settings are now handled by DashboardApp::settings_ui
}
