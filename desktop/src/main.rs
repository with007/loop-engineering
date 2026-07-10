#![windows_subsystem = "windows"]

use std::io::Write;
use std::num::NonZeroU32;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use tray_icon::menu::MenuEvent;
use winit::application::ApplicationHandler;
use winit::event::{StartCause, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop, EventLoopProxy};
use winit::raw_window_handle::HasWindowHandle;
use winit::window::WindowId;

mod config;
mod download;
mod server;
mod tray;
mod icon_data;

use config::Config;
use server::{find_available_port, Server};

// ── 文件日志（因为没有 console）────────────────────────────────────────────
static LOG_PATH: std::sync::OnceLock<String> = std::sync::OnceLock::new();
/// Set while a download_update is in progress — prevents concurrent downloads.
static DOWNLOAD_IN_PROGRESS: AtomicBool = AtomicBool::new(false);
/// Timeout for update download (30MB over GitHub should finish in <5min).
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(600);

fn init_log(exe_dir: &std::path::Path) {
    let path = exe_dir.join("dashboard.log").to_string_lossy().to_string();
    LOG_PATH.set(path.clone()).ok();
    let _ = std::fs::write(&path, String::new()); // 清空
    log_msg("=== Loop Dashboard started ===");
}

fn log_msg(msg: &str) {
    if let Some(path) = LOG_PATH.get() {
        let ts = chrono_now();
        let line = format!("{} {}\n", ts, msg);
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = f.write_all(line.as_bytes());
            let _ = f.flush();
        }
    }
}

fn chrono_now() -> String {
    use std::time::SystemTime;
    let d = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();
    format!("[{}.{:03}]", d.as_secs(), d.subsec_millis())
}

macro_rules! log {
    ($($arg:tt)*) => { log_msg(&format!($($arg)*)) };
}

// ── AppState ──────────────────────────────────────────────────────────────

pub struct AppState {
    pub loop_running: bool,
    pub loop_paused: bool,
    pub heartbeat: String,
    pub current_task: String,
    pub pending_merge: u32,
    pub port: u16,
    pub autostart: bool,
    pub auto_open_browser: bool,
}

// ── UserEvent ─────────────────────────────────────────────────────────────

#[derive(Debug)]
enum UserEvent {
    MenuEvent(tray_icon::menu::MenuEvent),
    /// Background poll result — server status check completed
    PollResult { running: bool, paused: bool },
    /// Background poll failed (server down, restarting in background)
    PollServerDown,
    /// Update check found and downloaded a new version
    UpdateReady { version: String },
    /// Download progress (0-100 percent, bytes_per_sec)
    UpdateProgress(u32, f64),
    /// Update check status (for tray tooltip feedback)
    UpdateStatus(String),
}

// ── GlutinWindowContext ───────────────────────────────────────────────────

struct GlutinWindowContext {
    window: winit::window::Window,
    gl_context: glutin::context::PossiblyCurrentContext,
    gl_display: glutin::display::Display,
    gl_surface: glutin::surface::Surface<glutin::surface::WindowSurface>,
}

impl GlutinWindowContext {
    #[allow(unsafe_code)]
    unsafe fn new(event_loop: &ActiveEventLoop) -> Self {
        use glutin::context::NotCurrentGlContext;
        use glutin::display::GetGlDisplay;
        use glutin::display::GlDisplay;
        use glutin::prelude::GlSurface;

        let winit_window_builder = winit::window::WindowAttributes::default()
            .with_resizable(false)
            .with_inner_size(winit::dpi::LogicalSize {
                width: 380.0,
                height: 440.0,
            })
            .with_title("Loop Dashboard 设置")
            .with_visible(false);

        let config_template_builder = glutin::config::ConfigTemplateBuilder::new()
            .prefer_hardware_accelerated(None)
            .with_depth_size(0)
            .with_stencil_size(0)
            .with_transparency(false);

        log!("GlutinWindowContext: building display...");
        let (mut window, gl_config) =
            glutin_winit::DisplayBuilder::new()
                .with_preference(glutin_winit::ApiPreference::FallbackEgl)
                .with_window_attributes(Some(winit_window_builder.clone()))
                .build(
                    event_loop,
                    config_template_builder,
                    |mut config_iterator| {
                        config_iterator.next().expect(
                            "failed to find a matching configuration for creating glutin config",
                        )
                    },
                )
                .expect("failed to create gl_config");
        let gl_display = gl_config.display();
        log!("GlutinWindowContext: gl_config found");

        let raw_window_handle = window.as_ref().map(|w| {
            w.window_handle()
                .expect("failed to get window handle")
                .as_raw()
        });
        let context_attributes =
            glutin::context::ContextAttributesBuilder::new().build(raw_window_handle);
        let not_current_gl_context = unsafe {
            gl_display
                .create_context(&gl_config, &context_attributes)
                .unwrap_or_else(|_| {
                    log!("GlutinWindowContext: retrying with GLES fallback");
                    let fallback_attrs = glutin::context::ContextAttributesBuilder::new()
                        .with_context_api(glutin::context::ContextApi::Gles(None))
                        .build(raw_window_handle);
                    gl_config
                        .display()
                        .create_context(&gl_config, &fallback_attrs)
                        .expect("failed to create context even with fallback attributes")
                })
        };

        let window = window.take().unwrap_or_else(|| {
            log!("GlutinWindowContext: finalizing window");
            glutin_winit::finalize_window(event_loop, winit_window_builder.clone(), &gl_config)
                .expect("failed to finalize glutin window")
        });

        // Center the window on the primary monitor
        if let Some(monitor) = window.current_monitor() {
            let win_size = window.inner_size();
            let mon_size = monitor.size();
            let x = mon_size.width.saturating_sub(win_size.width) / 2;
            let y = mon_size.height.saturating_sub(win_size.height) / 2;
            let _ = window.set_outer_position(winit::dpi::PhysicalPosition::new(x, y));
        }
        let (width, height): (u32, u32) = window.inner_size().into();
        let width = NonZeroU32::new(width).unwrap_or(NonZeroU32::MIN);
        let height = NonZeroU32::new(height).unwrap_or(NonZeroU32::MIN);
        let surface_attributes =
            glutin::surface::SurfaceAttributesBuilder::<glutin::surface::WindowSurface>::new()
                .build(
                    window
                        .window_handle()
                        .expect("failed to get window handle")
                        .as_raw(),
                    width,
                    height,
                );
        let gl_surface = unsafe {
            gl_display
                .create_window_surface(&gl_config, &surface_attributes)
                .unwrap()
        };
        log!("GlutinWindowContext: surface created");
        let gl_context = not_current_gl_context.make_current(&gl_surface).unwrap();

        gl_surface
            .set_swap_interval(
                &gl_context,
                glutin::surface::SwapInterval::Wait(NonZeroU32::MIN),
            )
            .unwrap();

        log!("GlutinWindowContext: ready");
        Self {
            window,
            gl_context,
            gl_display,
            gl_surface,
        }
    }

    fn window(&self) -> &winit::window::Window {
        &self.window
    }

    fn resize(&self, physical_size: winit::dpi::PhysicalSize<u32>) {
        use glutin::surface::GlSurface;
        self.gl_surface.resize(
            &self.gl_context,
            physical_size.width.try_into().unwrap(),
            physical_size.height.try_into().unwrap(),
        );
    }

    fn swap_buffers(&self) -> glutin::error::Result<()> {
        use glutin::surface::GlSurface;
        self.gl_surface.swap_buffers(&self.gl_context)
    }

    fn get_proc_address(&self, addr: &std::ffi::CStr) -> *const std::ffi::c_void {
        use glutin::display::GlDisplay;
        self.gl_display.get_proc_address(addr)
    }
}

enum WindowType {
    Settings,
    UpdateReady { version: String },
}

// ── WindowState ───────────────────────────────────────────────────────────

struct WindowState {
    window_type: WindowType,
    gl_window: GlutinWindowContext,
    gl: Arc<glow::Context>,
    egui_glow: egui_glow::EguiGlow,
    /// Editable text — persists across frames (not reset on each render)
    port_str: String,
    autostart: bool,
    auto_open_browser: bool,
    update_status: Option<String>,
    update_progress: Option<u32>,
    update_speed: Option<f64>,
    /// Pending update version (downloaded, waiting for user action)
    update_pending_version: Option<String>,
}

impl WindowState {
    fn new(
        event_loop: &ActiveEventLoop,
        window_type: WindowType,
        port: u16,
        autostart: bool,
        auto_open_browser: bool,
        update_status: Option<String>,
        update_progress: Option<u32>,
        update_speed: Option<f64>,
        update_pending_version: Option<String>,
    ) -> Self {
        log!("WindowState: creating GL context...");
        let gl_window = unsafe { GlutinWindowContext::new(event_loop) };
        let gl = unsafe {
            glow::Context::from_loader_function(|s| {
                let s = std::ffi::CString::new(s)
                    .expect("failed to construct C string from string for gl proc address");
                gl_window.get_proc_address(&s)
            })
        };
        let gl = Arc::new(gl);

        log!("WindowState: creating EguiGlow...");
        let egui_glow = egui_glow::EguiGlow::new(event_loop, gl.clone(), None, None, true);

        // Load CJK font
        if let Some(cjk) = find_cjk_font() {
            let mut fonts = egui::FontDefinitions::default();
            fonts.font_data.insert(
                "cjk".to_string(),
                std::sync::Arc::new(egui::FontData::from_owned(cjk)),
            );
            fonts
                .families
                .entry(egui::FontFamily::Proportional)
                .or_default()
                .insert(0, "cjk".to_string());
            fonts
                .families
                .entry(egui::FontFamily::Monospace)
                .or_default()
                .push("cjk".to_string());
            egui_glow.egui_ctx.set_fonts(fonts);
            log!("WindowState: CJK font loaded");
        } else {
            log!("WindowState: NO CJK FONT FOUND");
        }

        log!("WindowState: created");
        Self {
            window_type,
            gl_window,
            gl,
            egui_glow,
            port_str: port.to_string(),
            autostart,
            auto_open_browser,
            update_status,
            update_progress,
            update_speed,
            update_pending_version,
        }
    }

    fn set_update_status(&mut self, text: Option<String>) {
        self.update_status = text;
    }
    fn set_update_progress(&mut self, pct: Option<u32>) {
        self.update_progress = pct;
    }
    fn set_update_speed(&mut self, speed: Option<f64>) {
        self.update_speed = speed;
    }
    fn set_update_pending_version(&mut self, version: Option<String>) {
        self.update_pending_version = version;
    }

    fn render(&mut self) -> SettingsAction {
        let mut action = SettingsAction::None;

        let is_update_dialog = matches!(self.window_type, WindowType::UpdateReady { .. });
        let update_version = match &self.window_type {
            WindowType::UpdateReady { version } => Some(version.clone()),
            _ => None,
        };

        // Extract fields before the closure to avoid borrow-of-self conflicts
        let port_str = &mut self.port_str;
        let autostart_val = &mut self.autostart;
        let auto_open_val = &mut self.auto_open_browser;
        let update_status = &self.update_status;
        let update_progress = &self.update_progress;
        let update_pending = &self.update_pending_version;

        self.egui_glow.run(self.gl_window.window(), |egui_ctx| {
            if egui_ctx.input(|i| i.viewport().close_requested()) {
                action = SettingsAction::Close;
                return;
            }

            egui::CentralPanel::default().show(egui_ctx, |ui| {
                // ── Update-ready dialog (compact) ──
                if is_update_dialog {
                    if let Some(ref ver) = update_version {
                        ui.vertical_centered(|ui| {
                            ui.heading("更新已就绪");
                            ui.add_space(8.0);
                            ui.label(format!("Loop Dashboard v{} 已下载完成。", ver));
                            ui.add_space(8.0);
                            ui.horizontal(|ui| {
                                if ui
                                    .add(egui::Button::new(
                                        egui::RichText::new("立即重启安装")
                                            .color(egui::Color32::WHITE),
                                    )
                                    .fill(egui::Color32::from_rgb(0, 120, 30)))
                                    .clicked()
                                {
                                    action = SettingsAction::ApplyUpdate;
                                }
                                if ui.button("稍后提醒").clicked() {
                                    action = SettingsAction::DeferUpdate;
                                }
                            });
                        });
                    }
                    return;
                }

                // ── Settings window (full) ──
                ui.vertical_centered(|ui| {
                    ui.heading("Loop Dashboard 设置");
                    ui.label(
                        egui::RichText::new(format!("v{}", env!("CARGO_PKG_VERSION")))
                            .color(egui::Color32::GRAY),
                    );
                });
                ui.separator();

                // ── Server settings ──
                ui.horizontal(|ui| {
                    ui.label("端口号:");
                    ui.add(
                        egui::TextEdit::singleline(port_str).desired_width(80.0),
                    );
                });
                ui.label("修改端口后需重启生效");
                ui.add_space(4.0);
                ui.checkbox(autostart_val, "开机自启");
                ui.checkbox(auto_open_val, "启动时自动打开 Dashboard");
                ui.add_space(8.0);

                // ── Updates ──
                ui.separator();
                ui.vertical_centered(|ui| {
                    ui.heading("更新");
                });
                ui.add_space(4.0);

                // Status text
                if let Some(ref status) = update_status {
                    ui.label(status);
                } else {
                    ui.label("暂无更新状态");
                }

                // Progress bar
                if let Some(pct) = update_progress {
                    ui.add(
                        egui::ProgressBar::new(*pct as f32 / 100.0)
                            .desired_width(200.0)
                            .text(format!("{}%", pct)),
                    );
                }

                // Update ready — show restart/defer buttons
                if let Some(ref ver) = update_pending {
                    ui.add_space(8.0);
                    ui.colored_label(
                        egui::Color32::from_rgb(100, 255, 100),
                        format!("✅ v{} 已下载完成", ver),
                    );
                    ui.add_space(4.0);
                    ui.horizontal(|ui| {
                        if ui
                            .add(egui::Button::new(
                                egui::RichText::new("立即重启安装")
                                    .color(egui::Color32::WHITE),
                            )
                            .fill(egui::Color32::from_rgb(0, 120, 30)))
                            .clicked()
                        {
                            action = SettingsAction::ApplyUpdate;
                        }
                        if ui.button("稍后提醒").clicked() {
                            action = SettingsAction::DeferUpdate;
                        }
                    });
                }

                ui.add_space(4.0);
                if ui.button("检查更新").clicked() {
                    action = SettingsAction::CheckUpdates;
                }
                if ui
                    .add(egui::Link::new("📦 手动下载最新版 (GitHub)"))
                    .clicked()
                {
                    action = SettingsAction::OpenGitHub;
                }

                ui.add_space(12.0);
                ui.separator();

                // ── Save / Cancel ──
                ui.horizontal(|ui| {
                    if ui.button("保存").clicked() {
                        log!("settings: save clicked, port={}, autostart={}, auto_open={}",
                            port_str, autostart_val, auto_open_val);
                        action = SettingsAction::Save {
                            port: port_str.parse::<u16>().unwrap_or(8765),
                            autostart: *autostart_val,
                            auto_open_browser: *auto_open_val,
                        };
                    }
                    if ui.button("取消").clicked() {
                        log!("settings: cancel clicked");
                        action = SettingsAction::Close;
                    }
                });
            });
        });

        // Paint and swap
        unsafe {
            use glow::HasContext as _;
            self.gl.clear_color(0.15, 0.15, 0.15, 1.0);
            self.gl.clear(glow::COLOR_BUFFER_BIT);
        }
        self.egui_glow.paint(self.gl_window.window());
        let _ = self.gl_window.swap_buffers();

        action
    }
}

enum SettingsAction {
    None,
    Close,
    Save { port: u16, autostart: bool, auto_open_browser: bool },
    CheckUpdates,
    OpenGitHub,
    /// User clicked "restart now" in the update-ready UI
    ApplyUpdate,
    /// User clicked "later" in the update-ready UI
    DeferUpdate,
}

// ── App ───────────────────────────────────────────────────────────────────

struct App {
    tray_icon: Option<tray_icon::TrayIcon>,
    menu_items: Option<tray::TrayMenuItems>,
    menu_ids: Option<tray::TrayMenuIds>,
    windows: Vec<WindowState>,
    state: Arc<Mutex<AppState>>,
    server: Arc<Mutex<Server>>,
    python_exe: Arc<String>,
    app_dir: Arc<String>,
    exe_dir: std::path::PathBuf,
    last_poll: Instant,
    proxy: EventLoopProxy<UserEvent>,
    test_mode: bool,
    test_step: u32,
    test_timer: Instant,
    last_heartbeat: Instant,
    /// Pending update version (downloaded, waiting for user to restart)
    update_pending_version: Option<String>,
    /// Current update status message (shown in settings)
    update_status: Option<String>,
    /// Current download progress (0-100, shown in settings)
    update_progress: Option<u32>,
    /// Current download speed in bytes/sec (shown in settings)
    update_speed: Option<f64>,
    /// True if this is the first run (no settings file existed on startup)
    first_run: bool,
    /// Auto-open browser on startup (from config)
    auto_open_browser: bool,
}

impl ApplicationHandler<UserEvent> for App {
    fn new_events(&mut self, event_loop: &ActiveEventLoop, cause: StartCause) {
        // Set Poll mode — always running regardless of window visibility
        event_loop.set_control_flow(ControlFlow::Poll);

        if cause == StartCause::Init {
            log!("new_events: Init — creating tray icon");
            let (tray_icon, menu_items, menu_ids) = tray::create_tray();
            self.tray_icon = Some(tray_icon);
            self.menu_items = Some(menu_items);
            self.menu_ids = Some(menu_ids);
            log!("new_events: tray icon created. Menu IDs: settings={:?} quit={:?}",
                self.menu_ids.as_ref().unwrap().settings,
                self.menu_ids.as_ref().unwrap().quit);

            // Auto-open settings window on first run
            if self.first_run {
                log!("new_events: first run — auto-opening settings window");
                self.open_settings_window(event_loop);
            }
        }

        // Heartbeat log every 2 seconds
        if self.last_heartbeat.elapsed().as_secs() >= 2 {
            self.last_heartbeat = Instant::now();
            log!("heartbeat: poll mode active");
        }

        // Keep rendering while any window is open
        for ws in &self.windows {
            ws.gl_window.window().request_redraw();
        }

        // ── Test mode ──
        if self.test_mode {
            let secs = self.test_timer.elapsed().as_secs();
            match self.test_step {
                0 => {
                    if secs >= 3 {
                        log!("test: step 0→1, opening settings panel");
                        self.open_settings_window(event_loop);
                        self.test_step = 1;
                        self.test_timer = Instant::now();
                    }
                }
                1 => {
                    if secs >= 1 {
                        log!("test: step 1→2, closing settings panel");
                        self.hide_settings_window();
                        self.test_step = 2;
                        self.test_timer = Instant::now();
                    }
                }
                2 => {
                    if secs >= 1 {
                        log!("test: step 2→3, stopping server before exit");
                        self.server.lock().unwrap().stop();
                        log!("test: ====== ALL TESTS PASSED ======");
                        std::process::exit(0);
                    }
                }
                _ => {}
            }
        }

        // Server polling every 10 seconds (background thread — don't block GUI)
        if self.last_poll.elapsed().as_secs() >= 10 {
            self.last_poll = Instant::now();
            log!("new_events: polling server status...");
            let port = { self.state.lock().unwrap().port };
            let state = self.state.clone();
            let server = self.server.clone();
            let python_exe = self.python_exe.clone();
            let app_dir = self.app_dir.clone();
            let proxy = self.proxy.clone();
            std::thread::spawn(move || {
                poll_background(port, &state, &server, &python_exe, &app_dir, &proxy);
            });
        }
    }

    fn user_event(&mut self, event_loop: &ActiveEventLoop, event: UserEvent) {
        match event {
            UserEvent::MenuEvent(e) => {
                log!("user_event: MenuEvent id={:?}", e.id);
                self.handle_menu_event(event_loop, e);
            }
            UserEvent::PollResult { running, paused } => {
                self.update_loop_state(running, paused);
            }
            UserEvent::PollServerDown => {
                self.update_loop_state(false, false);
            }
            UserEvent::UpdateReady { version } => {
                log!("user_event: UpdateReady v{}", version);
                self.update_pending_version = Some(version.clone());
                self.update_progress = Some(100);
                self.update_speed = None;
                // Update settings window if open
                if let Some(ws) = self.settings_window_mut() {
                    ws.set_update_progress(Some(100));
                    ws.set_update_speed(None);
                    ws.set_update_status(Some(format!("v{} 已就绪", version)));
                    ws.set_update_pending_version(Some(version.clone()));
                    ws.render();
                }
                // Open a separate update-ready dialog window
                self.open_update_dialog(event_loop, &version);
                if let Some(ref icon) = self.tray_icon {
                    let _ = icon.set_tooltip(Some(&format!("v{} 已就绪，重启以应用", version)));
                }
            }
            UserEvent::UpdateProgress(pct, speed) => {
                self.update_progress = Some(pct);
                let speed_val = if speed > 0.0 { Some(speed) } else { self.update_speed };
                self.update_speed = speed_val;
                if let Some(ws) = self.settings_window_mut() {
                    ws.set_update_progress(Some(pct));
                    ws.set_update_speed(speed_val);
                    let speed_str = format_speed(speed_val);
                    if speed_str.is_empty() {
                        ws.set_update_status(Some("下载中...".into()));
                    } else {
                        ws.set_update_status(Some(format!("下载中... {}", speed_str)));
                    }
                }
                if let Some(ref icon) = self.tray_icon {
                    let speed_str = format_speed(self.update_speed);
                    let msg = if speed_str.is_empty() {
                        "Downloading...".to_string()
                    } else {
                        format!("Downloading... {}", speed_str)
                    };
                    let _ = icon.set_tooltip(Some(&msg));
                }
                // Log progress at 10% intervals to avoid too much noise
                if pct % 10 == 0 {
                    log!("update: download progress {}%", pct);
                }
            }
            UserEvent::UpdateStatus(msg) => {
                self.update_status = Some(msg.clone());
                self.update_progress = None;
                if let Some(ws) = self.settings_window_mut() {
                    ws.set_update_status(Some(msg.clone()));
                    ws.set_update_progress(None);
                }
                if let Some(ref icon) = self.tray_icon {
                    let _ = icon.set_tooltip(Some(&msg));
                }
            }
        }
    }

    fn window_event(
        &mut self,
        _event_loop: &ActiveEventLoop,
        window_id: WindowId,
        event: WindowEvent,
    ) {
        // Find which window this event belongs to
        if self.find_window(window_id).is_none() {
            return;
        }

        match event {
            WindowEvent::CloseRequested => {
                log!("window_event: CloseRequested — hiding settings window");
                self.hide_settings_window();
            }
            WindowEvent::RedrawRequested => {
                // Handled below — we render in the event processing
            }
            WindowEvent::Resized(physical_size) => {
                if let Some(ref ws) = self.find_window(window_id) {
                    ws.gl_window.resize(physical_size);
                }
            }
            _ => {}
        }

        // Forward event to egui for input handling
        if let Some(ref mut ws) = self.find_window_mut(window_id) {
            let event_response = ws
                .egui_glow
                .on_window_event(ws.gl_window.window(), &event);

            if event_response.repaint {
                ws.gl_window.window().request_redraw();
            }

            // Render on RedrawRequested or after input events that need repaint
            if matches!(event, WindowEvent::RedrawRequested) || event_response.repaint {
                let action = ws.render();
                let is_settings = matches!(ws.window_type, WindowType::Settings);
                match action {
                    SettingsAction::Close => {
                        if is_settings {
                            self.hide_settings_window();
                        } else {
                            // Close non-settings windows (e.g. update dialog)
                            self.close_window(window_id);
                        }
                    }
                    SettingsAction::Save { port, autostart, auto_open_browser } => {
                        log!(
                            "settings: saving port={}, autostart={}, auto_open={}",
                            port, autostart, auto_open_browser
                        );
                        let cfg = Config { port, autostart, auto_open_browser };
                        cfg.save(&self.exe_dir);
                        // Update app state
                        {
                            let mut s = self.state.lock().unwrap();
                            s.port = port;
                            s.autostart = autostart;
                            s.auto_open_browser = auto_open_browser;
                        }
                        self.auto_open_browser = auto_open_browser;
                        if autostart {
                            enable_autostart();
                        } else {
                            disable_autostart();
                        }
                        self.hide_settings_window();
                    }
                    SettingsAction::CheckUpdates => {
                        // Check for pending update first
                        if let Some(ref ver) = self.update_pending_version {
                            log!("settings: apply pending update v{}", ver);
                            self.apply_pending_update();
                        } else {
                            log!("settings: check_updates clicked");
                            self.update_status = Some("Checking for updates...".into());
                            self.update_progress = None;
                            if let Some(ws) = self.settings_window_mut() {
                                ws.set_update_status(Some("Checking for updates...".into()));
                                ws.set_update_progress(None);
                            }
                            let proxy = self.proxy.clone();
                            std::thread::spawn(move || {
                                check_for_updates_inner(&proxy, true);
                            });
                        }
                    }
                    SettingsAction::ApplyUpdate => {
                        log!("settings: user clicked 'restart now' for update");
                        self.apply_pending_update();
                    }
                    SettingsAction::DeferUpdate => {
                        log!("settings: user clicked 'later' for update, deferring");
                        self.update_pending_version = None;
                        // Close all update dialogs
                        let update_ids: Vec<WindowId> = self.windows.iter()
                            .filter(|w| matches!(w.window_type, WindowType::UpdateReady { .. }))
                            .map(|w| w.gl_window.window().id())
                            .collect();
                        for id in update_ids {
                            self.close_window(id);
                        }
                        if let Some(ws) = self.settings_window_mut() {
                            ws.set_update_pending_version(None);
                            ws.set_update_status(Some("更新已推迟，重启后应用".into()));
                            ws.set_update_progress(None);
                            ws.set_update_speed(None);
                        }
                        if let Some(ref icon) = self.tray_icon {
                            let _ = icon.set_tooltip(Some("Loop Dashboard"));
                        }
                    }
                    SettingsAction::OpenGitHub => {
                        let releases_url = format!("{}/releases", UPDATE_SOURCE_URL);
                        log!("settings: open_github clicked, opening {}", releases_url);
                        let _ = open::that(&releases_url);
                    }
                    SettingsAction::None => {}
                }
            }
        }
    }

    fn resumed(&mut self, _event_loop: &ActiveEventLoop) {
        // No-op: we don't create windows on resume — tray-only startup
    }

    fn suspended(&mut self, _event_loop: &ActiveEventLoop) {
        // No-op
    }

    fn exiting(&mut self, _event_loop: &ActiveEventLoop) {
        log!("exiting: cleaning up server and GL resources");
        self.server.lock().unwrap().stop();
        log!("exiting: server stopped");
        for ws in &mut self.windows {
            ws.egui_glow.destroy();
        }
        log!("exiting: cleanup complete");
    }
}

// ── App methods ───────────────────────────────────────────────────────────

impl App {
    // ── Window helpers ────────────────────────────────────────────────────

    fn settings_window(&self) -> Option<&WindowState> {
        self.windows.iter().find(|w| matches!(w.window_type, WindowType::Settings))
    }
    fn settings_window_mut(&mut self) -> Option<&mut WindowState> {
        self.windows.iter_mut().find(|w| matches!(w.window_type, WindowType::Settings))
    }
    fn find_window_mut(&mut self, id: WindowId) -> Option<&mut WindowState> {
        self.windows.iter_mut().find(|w| w.gl_window.window().id() == id)
    }
    fn find_window(&self, id: WindowId) -> Option<&WindowState> {
        self.windows.iter().find(|w| w.gl_window.window().id() == id)
    }

    // ── open / hide ───────────────────────────────────────────────────────

    fn open_settings_window(&mut self, event_loop: &ActiveEventLoop) {
        log!("open_settings_window: creating new window");
        let (port, autostart, auto_open_browser) = {
            let s = self.state.lock().unwrap();
            (s.port, s.autostart, s.auto_open_browser)
        };
        let status = self.update_status.clone();
        let progress = self.update_progress;
        let speed = self.update_speed;
        let pending = self.update_pending_version.clone();
        let mut ws = WindowState::new(event_loop, WindowType::Settings, port, autostart, auto_open_browser, status, progress, speed, pending);

        // Render first frame BEFORE showing, so user doesn't see white flash
        log!("open_settings_window: rendering first frame...");
        ws.render();
        ws.gl_window.window().set_visible(true);
        ws.gl_window.window().request_redraw();
        log!("open_settings_window: window visible, redraw requested");

        self.windows.push(ws);
    }

    fn open_update_dialog(&mut self, event_loop: &ActiveEventLoop, version: &str) {
        log!("open_update_dialog: creating update-ready window for v{}", version);
        let (port, autostart, auto_open_browser) = {
            let s = self.state.lock().unwrap();
            (s.port, s.autostart, s.auto_open_browser)
        };
        let mut ws = WindowState::new(
            event_loop,
            WindowType::UpdateReady { version: version.to_string() },
            port, autostart, auto_open_browser,
            Some(format!("v{} 已就绪", version)),
            Some(100),
            None,
            Some(version.to_string()),
        );
        ws.render();
        ws.gl_window.window().set_visible(true);
        ws.gl_window.window().request_redraw();
        log!("open_update_dialog: window visible");
        self.windows.push(ws);
    }

    fn hide_settings_window(&mut self) {
        if let Some(pos) = self.windows.iter().position(|w| matches!(w.window_type, WindowType::Settings)) {
            let mut ws = self.windows.remove(pos);
            ws.gl_window.window().set_visible(false);
            ws.egui_glow.destroy();
            log!("hide_settings_window: window hidden and GL resources released");
        }
        // WindowState dropped here → GlutinWindowContext (window, GL context, surface) freed
    }

    fn close_window(&mut self, id: WindowId) {
        if let Some(pos) = self.windows.iter().position(|w| w.gl_window.window().id() == id) {
            let mut ws = self.windows.remove(pos);
            ws.gl_window.window().set_visible(false);
            ws.egui_glow.destroy();
            log!("close_window: window {:?} closed", id);
        }
    }

    fn apply_pending_update(&self) {
        // Try to apply any pending update via Velopack
        use velopack::sources;
        let source = sources::GithubSource::new(UPDATE_SOURCE_URL, None, true);
        match velopack::UpdateManager::new(source, None, None) {
            Ok(um) => {
                if let Some(asset) = um.get_update_pending_restart() {
                    log!("apply_pending_update: applying {} and restarting", asset.Version);
                    let _ = um.apply_updates_and_restart(&asset);
                } else {
                    log!("apply_pending_update: no pending update found on disk");
                }
            }
            Err(e) => {
                log!("apply_pending_update: failed to create UpdateManager: {:?}", e);
            }
        }
    }

    fn rebuild_menu(&mut self, running: bool, paused: bool) {
        if let (Some(ref mut items), Some(ref mut tray_icon)) =
            (&mut self.menu_items, &mut self.tray_icon)
        {
            let menu = tray::build_menu(items, running, paused);
            tray_icon.set_menu(Some(Box::new(menu)));
        }
    }

    fn update_loop_state(&mut self, running: bool, paused: bool) {
        let mut s = self.state.lock().unwrap();
        s.loop_running = running;
        s.loop_paused = paused;
        drop(s);
        self.rebuild_menu(running, paused);
    }

    fn handle_menu_event(&mut self, event_loop: &ActiveEventLoop, event: tray_icon::menu::MenuEvent) {
        let port = { self.state.lock().unwrap().port };
        let url = format!("http://localhost:{}", port);

        let ids = match &self.menu_ids {
            Some(ids) => ids,
            None => {
                log!("handle_menu_event: no menu_ids (should not happen)");
                return;
            }
        };
        let items = match &self.menu_items {
            Some(items) => items,
            None => return,
        };

        let id = &event.id;

        if id == &ids.add_project {
            log!("menu: add_project");
            let _ = open::that(format!("{}/setup", url));
        } else if id == &ids.settings {
            log!("menu: settings -> open_settings_window");
            self.open_settings_window(event_loop);
        } else if id == &ids.quit {
            log!("menu: QUIT -> stopping server and exiting");
            self.server.lock().unwrap().stop();
            log!("menu: QUIT -> server stopped, calling std::process::exit(0)");
            std::process::exit(0);
        } else {
            // Check per-project menu items
            let mut handled = false;
            for proj in &items.projects {
                if let Some(action) = proj.match_event(id) {
                    let encoded = proj.root.replace('\\', "/").replace(':', "%3A");
                    let project_url = format!("{}/?project={}", url, encoded);
                    match action {
                        tray::ProjectAction::OpenDashboard => {
                            log!("menu: project '{}' -> open_dashboard", proj.name);
                            let _ = open::that(&project_url);
                        }
                        tray::ProjectAction::Pause => {
                            log!("menu: project '{}' -> pause", proj.name);
                            let _ = ureq::post(&format!("{}/api/control/pause", url))
                                .send_empty();
                            self.update_loop_state(true, true);
                        }
                        tray::ProjectAction::Resume => {
                            log!("menu: project '{}' -> resume", proj.name);
                            let _ = ureq::delete(&format!("{}/api/control/pause", url))
                                .call();
                            self.update_loop_state(true, false);
                        }
                        tray::ProjectAction::Stop => {
                            log!("menu: project '{}' -> stop", proj.name);
                            let _ = ureq::post(&format!("{}/api/control/stop", url))
                                .send_empty();
                            self.update_loop_state(false, false);
                        }
                        tray::ProjectAction::Start => {
                            log!("menu: project '{}' -> start", proj.name);
                            let _ = ureq::post(&format!("{}/api/control/start", url))
                                .send_empty();
                            self.update_loop_state(true, false);
                        }
                    }
                    handled = true;
                    break;
                }
            }
            if !handled {
                log!("menu: UNKNOWN menu id");
            }
        }
    }
}

// ── main ──────────────────────────────────────────────────────────────────

fn main() {
    let exe_dir = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
    init_log(&exe_dir);

    // Velopack: handle pending updates, first-run/restarted hooks.
    // Must run before anything else — it may terminate/restart the process.
    velopack::VelopackApp::build()
        .on_first_run(|v| log_msg(&format!("Velopack: first run of v{}", v)))
        .on_restarted(|v| log_msg(&format!("Velopack: restarted after update to v{}", v)))
        .run();

    // Single-instance guard — only one tray icon per user session
    let _single_instance_mutex = unsafe {
        use windows::Win32::System::Threading::CreateMutexW;
        use windows::Win32::Foundation::{GetLastError, ERROR_ALREADY_EXISTS};
        let name = windows::core::w!("LoopEngineeringDashboard");
        let handle = CreateMutexW(None, true, name).expect("CreateMutexW failed");
        if GetLastError() == ERROR_ALREADY_EXISTS {
            log!("main: another instance already running, exiting");
            return;
        }
        log!("main: single-instance mutex acquired");
        handle
    };
    // handle lives for the process lifetime (never dropped, OS cleans up on exit)

    // 检测 --test 模式
    let test_mode = std::env::args().any(|a| a == "--test");
    if test_mode {
        log!("main: TEST MODE enabled");
    }

    // Detect first run (no settings file yet)
    let first_run = !exe_dir.join("dashboard-settings.json").exists();
    if first_run {
        log!("main: FIRST RUN detected — will open settings window");
    }

    let config = Config::load(&exe_dir);
    let mut port = find_available_port(config.port);
    log!(
        "main: config loaded, config_port={}, using_port={}, autostart={}",
        config.port,
        port,
        config.autostart
    );

    let state = Arc::new(Mutex::new(AppState {
        loop_running: false,
        loop_paused: false,
        heartbeat: String::new(),
        current_task: String::new(),
        pending_merge: 0,
        port,
        autostart: config.autostart,
        auto_open_browser: config.auto_open_browser,
    }));

    if config.autostart {
        enable_autostart();
    }

    let server = Arc::new(Mutex::new(Server::new()));
    let python_exe = Arc::new(find_python(&exe_dir));
    let app_dir = Arc::new(exe_dir.to_string_lossy().to_string());

    log!("main: python_exe={}, app_dir={}", *python_exe, *app_dir);

    // Try starting server with port retry
    let mut retries = 0;
    loop {
        log!("main: starting server on port {} (attempt {})", port, retries + 1);
        if server.lock().unwrap().start(port, &python_exe, &app_dir) {
            break;
        }
        retries += 1;
        if retries >= 5 {
            log!("main: FAILED to start server after {} attempts", retries);
            break;
        }
        let next = port + 1;
        log!("main: port {} failed, trying {}...", port, next);
        port = next;
        // Update state port
        if let Ok(mut s) = state.lock() {
            s.port = port;
        }
    }

    if config.auto_open_browser {
        log!("main: auto-opening browser at http://127.0.0.1:{}", port);
        let _ = open::that(format!("http://127.0.0.1:{}", port));
    }
    log!("main: server ready on port {}", port);

    // Build event loop with user events
    let event_loop = EventLoop::<UserEvent>::with_user_event()
        .build()
        .unwrap();
    let proxy = event_loop.create_proxy();

    // Resume any interrupted downloads from previous session
    resume_pending_downloads(&exe_dir, &proxy);

    // If an update was downloaded in a previous session but not applied (user
    // deferred), prompt immediately on this launch.
    check_pending_update_on_startup(&proxy);

    // Register MenuEvent handler — forwards to EventLoopProxy
    MenuEvent::set_event_handler(Some(move |event: tray_icon::menu::MenuEvent| {
        let _ = proxy.send_event(UserEvent::MenuEvent(event));
    }));
    log!("main: MenuEvent handler registered");

    // Spawn background update checker (first check after 2 min, then every 6 hours)
    let update_proxy = event_loop.create_proxy();
    spawn_update_checker(update_proxy);

    let mut app = App {
        tray_icon: None,
        menu_items: None,
        menu_ids: None,
        windows: Vec::new(),
        state,
        server,
        python_exe,
        app_dir,
        exe_dir,
        last_poll: Instant::now(),
        proxy: event_loop.create_proxy(),
        test_mode,
        test_step: 0,
        test_timer: Instant::now(),
        last_heartbeat: Instant::now(),
        update_pending_version: None,
        update_status: None,
        update_progress: None,
        update_speed: None,
        first_run,
        auto_open_browser: config.auto_open_browser,
    };

    log!("main: entering event_loop.run_app");
    if let Err(err) = event_loop.run_app(&mut app) {
        log!("main: event loop error: {:?}", err);
    }
    log!("main: event loop exited");
}

// ── poll_background (runs in a thread — never blocks the GUI) ──────────────

fn poll_background(
    port: u16,
    state: &Arc<Mutex<AppState>>,
    server: &Arc<Mutex<Server>>,
    python_exe: &str,
    app_dir: &str,
    proxy: &EventLoopProxy<UserEvent>,
) {
    if !server::is_port_open(port) {
        log!("poll: server down, restarting...");
        {
            let mut s = state.lock().unwrap();
            s.loop_running = false;
            s.loop_paused = false;
        }
        let _ = proxy.send_event(UserEvent::PollServerDown);
        let mut srv = server.lock().unwrap();
        let _ = srv.restart(port, python_exe, app_dir);
        return;
    }

    match ureq::get(&format!("http://localhost:{}/api/control/status", port)).call() {
        Ok(resp) => {
            if let Ok(json) = resp.into_body().read_json::<serde_json::Value>() {
                let running = json.get("running").and_then(|v| v.as_bool()).unwrap_or(false);
                let paused = json.get("paused").and_then(|v| v.as_bool()).unwrap_or(false);
                let _ = proxy.send_event(UserEvent::PollResult { running, paused });
            }
        }
        Err(e) => {
            log!("poll: HTTP error: {:?}", e);
        }
    }
}

// ── update checker (runs in a thread — never blocks the GUI) ─────────────

/// GitHub repo URL for update checks.
const UPDATE_SOURCE_URL: &str = "https://github.com/with007/loop-engineering";

/// On startup, check for any interrupted downloads from a previous session
/// and resume them automatically.
fn resume_pending_downloads(exe_dir: &std::path::Path, proxy: &EventLoopProxy<UserEvent>) {
    let packages_dir = packages_dir(exe_dir);
    let state_files = match std::fs::read_dir(&packages_dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().ends_with(".download-state.json"))
            .collect::<Vec<_>>(),
        Err(_) => return,
    };

    for entry in state_files {
        let state_path = entry.path();
        let content = match std::fs::read_to_string(&state_path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let state: serde_json::Value = match serde_json::from_str(&content) {
            Ok(v) => v,
            Err(_) => continue,
        };

        let url = state.get("url").and_then(|v| v.as_str()).unwrap_or("");
        let expected_size = state.get("expected_size").and_then(|v| v.as_u64()).unwrap_or(0);
        let version = state.get("version").and_then(|v| v.as_str()).unwrap_or("");

        // Extract filename from state path: "X.nupkg.download-state.json" → "X.nupkg"
        let state_name = state_path.file_name().unwrap().to_string_lossy();
        let filename = state_name
            .strip_suffix(".download-state.json")
            .unwrap_or(&state_name)
            .to_string();

        if url.is_empty() || expected_size == 0 || filename.is_empty() {
            continue;
        }

        log!("startup: resuming download of {} ({} bytes at {})", filename, url, expected_size);
        if DOWNLOAD_IN_PROGRESS.swap(true, Ordering::SeqCst) {
            continue; // shouldn't happen on startup, but be safe
        }

        let _ = proxy.send_event(UserEvent::UpdateProgress(0, 0.0));
        let proxy_dl = proxy.clone();
        let proxy_dl_done = proxy.clone();
        let pkg_dir = packages_dir.clone();
        let fname = filename.clone();
        let ver = version.to_string();
        let token: Option<&str> = None;
        let asset_url = url.to_string();

        std::thread::spawn(move || {
            let mut retry_delay = Duration::from_secs(30);
            let mut current_url = asset_url.clone();

            let result = loop {
                let proxy_retry = proxy_dl.clone();
                match download::download_with_resume(
                    &current_url, &pkg_dir, &fname, expected_size, token,
                    move |pct, speed| {
                        let _ = proxy_retry.send_event(UserEvent::UpdateProgress(pct, speed));
                    },
                ) {
                    Ok(path) => break Ok(path),
                    Err(e) => {
                        let is_permanent = e.contains("size mismatch")
                            || e.contains("404") || e.contains("403");
                        if is_permanent || retry_delay > Duration::from_secs(90) {
                            break Err(e);
                        }
                        // Try to refresh the download URL (SAS tokens may expire)
                        log!("startup: resume failed ({}), refreshing URL and retrying in {}s...",
                            e, retry_delay.as_secs());
                        if let Some(new_url) = download::get_api_asset_url(
                            UPDATE_SOURCE_URL, &ver, &fname,
                        ) {
                            if new_url != current_url {
                                let state_path = pkg_dir.join(format!("{}.download-state.json", fname));
                                if let Err(e2) = download::refresh_state_url(&state_path, &new_url) {
                                    log!("startup: refresh state URL failed: {}", e2);
                                } else {
                                    current_url = new_url;
                                }
                            }
                        }
                        std::thread::sleep(retry_delay);
                        retry_delay = retry_delay.mul_f64(1.5);
                    }
                }
            };

            DOWNLOAD_IN_PROGRESS.store(false, Ordering::SeqCst);
            match result {
                Ok(_) => {
                    log!("startup: resumed download of v{} completed", ver);
                    let _ = proxy_dl_done.send_event(UserEvent::UpdateReady { version: ver });
                }
                Err(e) => {
                    log!("startup: resumed download ultimately failed: {}", e);
                    // Only clean up for permanent errors, keep partial file for transient network errors
                    let error_str = e.to_string();
                    let is_permanent = error_str.contains("size mismatch") ||
                                      error_str.contains("404") ||
                                      error_str.contains("403");
                    if is_permanent {
                        let _ = std::fs::remove_file(pkg_dir.join(format!("{}.partial", fname)));
                        let _ = std::fs::remove_file(pkg_dir.join(format!("{}.download-state.json", fname)));
                    } else {
                        log!("startup: keeping partial file for resume (transient error: {})", e);
                    }
                    let _ = proxy_dl_done.send_event(UserEvent::UpdateStatus(format!("Resume failed: {}", e)));
                }
            }
        });

        break; // Only handle one pending download at a time
    }
}

/// Format bytes/sec into a human-readable speed string (e.g., "1.2 MB/s").
fn format_speed(speed: Option<f64>) -> String {
    match speed {
        None | Some(0.0) => String::new(),
        Some(bps) if bps < 1024.0 => format!("{} B/s", bps as u64),
        Some(bps) if bps < 1024.0 * 1024.0 => format!("{:.1} KB/s", bps / 1024.0),
        Some(bps) => format!("{:.1} MB/s", bps / (1024.0 * 1024.0)),
    }
}

/// Determine the packages directory. In a Velopack install the exe lives under
/// `current/` and packages are at root level (`current/../packages`). In a
/// portable install the exe is at root and packages are next to it.
fn packages_dir(exe_dir: &std::path::Path) -> std::path::PathBuf {
    // Velopack install: exe in `current/`, packages at root
    if exe_dir.file_name().map_or(false, |n| n == "current") {
        exe_dir.parent().map(|p| p.join("packages")).unwrap_or_else(|| exe_dir.join("packages"))
    } else {
        exe_dir.join("packages")
    }
}
/// On startup, check if a previously-downloaded update is waiting to be applied.
/// If so, fire UpdateReady immediately so the user gets prompted right away
/// (instead of waiting for the 30s background check). No-op if the app is not
/// running from a Velopack-installed layout (e.g. portable extraction).
fn check_pending_update_on_startup(proxy: &EventLoopProxy<UserEvent>) {
    use velopack::sources;
    let source = sources::GithubSource::new(UPDATE_SOURCE_URL, None, true);
    match velopack::UpdateManager::new(source, None, None) {
        Ok(um) => match um.get_update_pending_restart() {
            Some(asset) => {
                log!(
                    "startup: pending update v{} found on disk, firing UpdateReady",
                    asset.Version
                );
                let _ = proxy.send_event(UserEvent::UpdateProgress(100, 0.0));
                let _ = proxy.send_event(UserEvent::UpdateReady {
                    version: asset.Version,
                });
            }
            None => log!("startup: no pending update to apply"),
        },
        Err(e) => {
            // Expected when running from a portable/non-Velopack layout (no
            // Update.exe / sq.version manifest). Silently skip — the 30s
            // background checker will still run and try.
            log!(
                "startup: pending-update check skipped (UpdateManager init failed: {:?})",
                e
            );
        }
    }
}

/// Compare two semver strings. Returns true if `remote` > `current`.
fn is_newer_version(remote: &str, current: &str) -> bool {
    let parse = |s: &str| -> (u32, u32, u32) {
        let parts: Vec<u32> = s.split('.')
            .filter_map(|p| p.parse().ok())
            .collect();
        (
            parts.first().copied().unwrap_or(0),
            parts.get(1).copied().unwrap_or(0),
            parts.get(2).copied().unwrap_or(0),
        )
    };
    parse(remote) > parse(current)
}

/// Check for updates via a single GitHub API call (replaces Velopack's 11+ request chain).
///
/// Velopack's `GithubSource::get_release_feed()` fetches `releases?per_page=10`
/// and then downloads `releases.{channel}.json` from each release — up to 11
/// serial HTTP requests.  From China each request can take 10-30 s, so the
/// check alone takes 2-5 minutes before the download even starts.
///
/// We only need the latest release, so one call to `/releases?per_page=1`
/// suffices.  We use the list endpoint instead of `/releases/latest` because
/// the latter returns 404 when all releases are marked as pre-releases.
///
/// Velopack is still used for applying the update (`apply_pending_update`).
fn check_for_updates_inner(proxy: &EventLoopProxy<UserEvent>, manual: bool) {
    let check_start = Instant::now();
    log!(
        "update: checking (source={}, manual={})",
        UPDATE_SOURCE_URL,
        manual
    );

    // ── 1. Single API call to GitHub ────────────────────────────────────
    // Use /releases?per_page=1 instead of /releases/latest because
    // /releases/latest returns 404 when all releases are pre-releases.
    let api_url = "https://api.github.com/repos/with007/loop-engineering/releases?per_page=1";

    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(30)))
        .timeout_connect(Some(Duration::from_secs(10)))
        .build()
        .into();

    let req = agent
        .get(api_url)
        .header("Accept", "application/vnd.github.v3+json")
        .header("User-Agent", "LoopDashboard/1.0");

    let response = match req.call() {
        Ok(resp) => resp,
        Err(e) => {
            log!("update: API request failed after {:?}: {:?}", check_start.elapsed(), e);
            let _ = proxy.send_event(UserEvent::UpdateStatus(format!("Update check failed: {}", e)));
            return;
        }
    };

    let releases: Vec<serde_json::Value> = match response.into_body().read_json() {
        Ok(v) => match v {
            serde_json::Value::Array(arr) => arr,
            _ => {
                log!("update: unexpected response format after {:?}", check_start.elapsed());
                let _ = proxy.send_event(UserEvent::UpdateStatus("Unexpected response".into()));
                return;
            }
        },
        Err(e) => {
            log!("update: failed to parse response after {:?}: {:?}", check_start.elapsed(), e);
            let _ = proxy.send_event(UserEvent::UpdateStatus(format!("Failed to parse response: {}", e)));
            return;
        }
    };

    let latest = match releases.first() {
        Some(r) => r,
        None => {
            log!("update: no releases found after {:?}", check_start.elapsed());
            let _ = proxy.send_event(UserEvent::UpdateStatus("No releases available".into()));
            return;
        }
    };

    let tag_name = latest.get("tag_name").and_then(|v| v.as_str()).unwrap_or("");
    let version = tag_name.strip_prefix('v').unwrap_or(tag_name);

    if version.is_empty() {
        log!("update: no tag_name in response after {:?}", check_start.elapsed());
        let _ = proxy.send_event(UserEvent::UpdateStatus("No release found".into()));
        return;
    }

    // ── 2. Version comparison ───────────────────────────────────────────
    let current = env!("CARGO_PKG_VERSION");
    if !is_newer_version(version, current) {
        log!("update: up to date (current=v{}, remote=v{}), check took {:?}",
            current, version, check_start.elapsed());
        let _ = proxy.send_event(UserEvent::UpdateStatus("Already up to date".into()));
        return;
    }

    // ── 3. Find .nupkg asset ────────────────────────────────────────────
    let assets = match latest.get("assets").and_then(|v| v.as_array()) {
        Some(a) => a,
        None => {
            log!("update: no assets in response after {:?}", check_start.elapsed());
            let _ = proxy.send_event(UserEvent::UpdateStatus("No assets found".into()));
            return;
        }
    };

    let nupkg = assets.iter().find(|a| {
        a.get("name")
            .and_then(|v| v.as_str())
            .map(|n| n.ends_with(".nupkg"))
            .unwrap_or(false)
    });

    let nupkg = match nupkg {
        Some(a) => a,
        None => {
            log!("update: no .nupkg asset found after {:?}", check_start.elapsed());
            let _ = proxy.send_event(UserEvent::UpdateStatus("No update package found".into()));
            return;
        }
    };

    let filename = nupkg.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let expected_size = nupkg.get("size").and_then(|v| v.as_u64()).unwrap_or(0);
    // Prefer the GitHub API asset endpoint (api.github.com) over the github.com
    // download URL — some networks block github.com but allow api.github.com.
    let api_asset_url = nupkg.get("url").and_then(|v| v.as_str()).map(|s| s.to_string());

    log!("update: found v{} (size={} bytes), check took {:?}, downloading...",
        version, expected_size, check_start.elapsed());

    // Notify user that a new version is being downloaded
    let _ = proxy.send_event(UserEvent::UpdateStatus(format!("Found v{}, downloading...", version)));

    // ── 4. Guard: only one download at a time ───────────────────────────
    if DOWNLOAD_IN_PROGRESS.swap(true, Ordering::SeqCst) {
        log!("update: download already in progress, skipping");
        return;
    }

    // Show immediate feedback — first bytes may take a while on slow links
    let _ = proxy.send_event(UserEvent::UpdateProgress(0, 0.0));

    let download_start = Instant::now();
    let asset_url = api_asset_url.unwrap_or_else(|| {
        download::get_github_release_url(UPDATE_SOURCE_URL, version, &filename)
            .unwrap_or_default()
    });
    if asset_url.is_empty() {
        log!("update: failed to resolve asset URL for v{}", version);
        let _ = proxy.send_event(UserEvent::UpdateStatus("Failed to resolve download URL".into()));
        DOWNLOAD_IN_PROGRESS.store(false, Ordering::SeqCst);
        return;
    }

    // ── 5. Determine packages directory ─────────────────────────────────
    let exe_dir = match std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
    {
        Some(dir) => dir,
        None => {
            log!("update: cannot determine exe directory");
            DOWNLOAD_IN_PROGRESS.store(false, Ordering::SeqCst);
            return;
        }
    };
    let packages_dir = packages_dir(&exe_dir);

    let version_down = version.to_string();
    let proxy_dl = proxy.clone();
    let proxy_dl_done = proxy.clone();

    // ── 6. Spawn download thread ────────────────────────────────────────
    std::thread::spawn(move || {
        let token: Option<&str> = None;
        let mut retry_delay = Duration::from_secs(30);

        let result = loop {
            let proxy_dl_attempt = proxy_dl.clone();
            match download::download_with_resume(
                &asset_url,
                &packages_dir,
                &filename,
                expected_size,
                token,
                move |pct, speed| {
                    let _ = proxy_dl_attempt.send_event(UserEvent::UpdateProgress(pct, speed));
                },
            ) {
                Ok(path) => break Ok(path),
                Err(e) => {
                    let is_permanent = e.contains("size mismatch")
                        || e.contains("404")
                        || e.contains("403");
                    if is_permanent || retry_delay > Duration::from_secs(90) {
                        break Err(e);
                    }
                    log!("update: download failed ({}), retrying in {}s...",
                        e, retry_delay.as_secs());
                    std::thread::sleep(retry_delay);
                    retry_delay = retry_delay.mul_f64(1.5);
                }
            }
        };

        DOWNLOAD_IN_PROGRESS.store(false, Ordering::SeqCst);

        match result {
            Ok(_final_path) => {
                log!("update: v{} downloaded successfully (size={} bytes) in {:?}",
                    version_down, expected_size, download_start.elapsed());
                log!("update: sending UpdateReady event for v{}", version_down);
                let send_result = proxy_dl_done.send_event(UserEvent::UpdateReady { version: version_down.clone() });
                log!("update: UpdateReady event sent for v{} (result={:?})", version_down, send_result);
            }
            Err(e) => {
                log!("update: download failed after {:?}: {}", download_start.elapsed(), e);
                let _ = proxy_dl_done.send_event(UserEvent::UpdateStatus(format!("Download failed: {}", e)));
                // Only clean up for permanent errors, keep partial file for transient network errors
                let error_str = e.to_string();
                let is_permanent = error_str.contains("size mismatch") ||
                                  error_str.contains("404") ||
                                  error_str.contains("403");
                if is_permanent {
                    let _ = std::fs::remove_file(packages_dir.join(format!("{}.partial", filename)));
                    let _ = std::fs::remove_file(packages_dir.join(format!("{}.download-state.json", filename)));
                } else {
                    log!("update: keeping partial file for resume (transient error: {})", e);
                }
            }
        }
    });

    // Timeout watchdog — log if download takes longer than expected
    std::thread::spawn(move || {
        std::thread::sleep(DOWNLOAD_TIMEOUT);
        if DOWNLOAD_IN_PROGRESS.load(Ordering::SeqCst) {
            log!("update: download still running after {:?}", DOWNLOAD_TIMEOUT);
        }
    });
}

/// Spawn a background thread that periodically checks for updates.
/// First check after 30 seconds, then every 30 minutes.
fn spawn_update_checker(proxy: EventLoopProxy<UserEvent>) {
    std::thread::spawn(move || {
        // Initial delay — let the app settle
        std::thread::sleep(std::time::Duration::from_secs(30));
        check_for_updates_inner(&proxy, false);

        // Periodic checks
        loop {
            std::thread::sleep(std::time::Duration::from_secs(30 * 60));
            check_for_updates_inner(&proxy, false);
        }
    });
}

// ── helpers ───────────────────────────────────────────────────────────────

fn find_python(exe_dir: &std::path::Path) -> String {
    let embedded = exe_dir.join("python").join("python.exe");
    if embedded.exists() {
        embedded.to_string_lossy().to_string()
    } else {
        "python".to_string()
    }
}

fn enable_autostart() {
    let exe = std::env::current_exe().unwrap();
    let _ = auto_launch::AutoLaunchBuilder::new()
        .set_app_name("LoopDashboard")
        .set_app_path(&exe.to_string_lossy())
        .build()
        .and_then(|a| a.enable());
}

fn disable_autostart() {
    let _ = auto_launch::AutoLaunchBuilder::new()
        .set_app_name("LoopDashboard")
        .set_app_path(&std::env::current_exe().unwrap().to_string_lossy())
        .build()
        .and_then(|a| a.disable());
}

fn find_cjk_font() -> Option<Vec<u8>> {
    let fonts = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msgothic.ttc",
    ];
    for path in &fonts {
        if let Ok(data) = std::fs::read(path) {
            return Some(data);
        }
    }
    None
}
