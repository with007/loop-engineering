#![windows_subsystem = "windows"]

use std::io::Write;
use std::num::NonZeroU32;
use std::sync::{Arc, Mutex};
use std::time::Instant;

use tray_icon::menu::MenuEvent;
use winit::application::ApplicationHandler;
use winit::event::{StartCause, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop, EventLoopProxy};
use winit::raw_window_handle::HasWindowHandle;
use winit::window::WindowId;

mod config;
mod server;
mod tray;

use config::Config;
use server::{find_available_port, Server};

// ── 文件日志（因为没有 console）────────────────────────────────────────────
static LOG_PATH: std::sync::OnceLock<String> = std::sync::OnceLock::new();

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
}

// ── UserEvent ─────────────────────────────────────────────────────────────

#[derive(Debug)]
enum UserEvent {
    MenuEvent(tray_icon::menu::MenuEvent),
    /// Background poll result — server status check completed
    PollResult { running: bool, paused: bool },
    /// Background poll failed (server down, restarting in background)
    PollServerDown,
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
                height: 280.0,
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
        let fallback_context_attributes = glutin::context::ContextAttributesBuilder::new()
            .with_context_api(glutin::context::ContextApi::Gles(None))
            .build(raw_window_handle);
        let not_current_gl_context = unsafe {
            gl_display
                .create_context(&gl_config, &context_attributes)
                .unwrap_or_else(|_| {
                    log!("GlutinWindowContext: retrying with GLES fallback");
                    gl_config
                        .display()
                        .create_context(&gl_config, &fallback_context_attributes)
                        .expect("failed to create context even with fallback attributes")
                })
        };

        let window = window.take().unwrap_or_else(|| {
            log!("GlutinWindowContext: finalizing window");
            glutin_winit::finalize_window(event_loop, winit_window_builder.clone(), &gl_config)
                .expect("failed to finalize glutin window")
        });
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

// ── WindowState ───────────────────────────────────────────────────────────

struct WindowState {
    gl_window: GlutinWindowContext,
    gl: Arc<glow::Context>,
    egui_glow: egui_glow::EguiGlow,
    port: u16,
    autostart: bool,
    settings_path: std::path::PathBuf,
}

impl WindowState {
    fn new(
        event_loop: &ActiveEventLoop,
        port: u16,
        autostart: bool,
        settings_path: std::path::PathBuf,
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
            gl_window,
            gl,
            egui_glow,
            port,
            autostart,
            settings_path,
        }
    }

    fn render(&mut self) -> SettingsAction {
        let mut action = SettingsAction::None;
        let mut port_str = self.port.to_string();
        let mut autostart_val = self.autostart;

        self.egui_glow.run(self.gl_window.window(), |egui_ctx| {
            if egui_ctx.input(|i| i.viewport().close_requested()) {
                log!("settings: close_requested by user");
                action = SettingsAction::Close;
                return;
            }

            egui::CentralPanel::default().show(egui_ctx, |ui| {
                ui.vertical_centered(|ui| {
                    ui.heading("Loop Dashboard 设置");
                });
                ui.separator();
                ui.horizontal(|ui| {
                    ui.label("端口号:");
                    ui.add(
                        egui::TextEdit::singleline(&mut port_str).desired_width(80.0),
                    );
                });
                ui.label("修改端口后需重启生效");
                ui.add_space(8.0);
                ui.checkbox(&mut autostart_val, "开机自启");
                ui.add_space(16.0);
                ui.horizontal(|ui| {
                    if ui.button("保存").clicked() {
                        log!("settings: save clicked, port={}, autostart={}", port_str, autostart_val);
                        action = SettingsAction::Save {
                            port: port_str.parse::<u16>().unwrap_or(8765),
                            autostart: autostart_val,
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
    Save { port: u16, autostart: bool },
}

// ── App ───────────────────────────────────────────────────────────────────

struct App {
    tray_icon: Option<tray_icon::TrayIcon>,
    menu_items: Option<tray::TrayMenuItems>,
    menu_ids: Option<tray::TrayMenuIds>,
    settings_window: Option<WindowState>,
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
        }

        // Heartbeat log every 2 seconds
        if self.last_heartbeat.elapsed().as_secs() >= 2 {
            self.last_heartbeat = Instant::now();
            log!("heartbeat: poll mode active");
        }

        // Keep rendering while settings window is open
        if let Some(ref ws) = self.settings_window {
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
                        log!("test: step 2→3, calling std::process::exit(0)");
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
                let mut s = self.state.lock().unwrap();
                s.loop_running = running;
                s.loop_paused = paused;
                drop(s);
                if let Some(ref items) = self.menu_items {
                    let status_text = if running && paused {
                        "Loop: 已暂停 ⏸"
                    } else if running {
                        "Loop: 运行中 ●"
                    } else {
                        "Loop: 未启动 ○"
                    };
                    let _ = items.status.set_text(status_text);
                }
                self.rebuild_menu(running, paused);
            }
            UserEvent::PollServerDown => {
                // Server was down, restart was triggered in background
                if let Some(ref items) = self.menu_items {
                    let _ = items.status.set_text("Loop: ⚠ 服务器重连中...");
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
        // Only process events for our settings window
        let settings_window_id = match &self.settings_window {
            Some(ref ws) => ws.gl_window.window().id(),
            None => return,
        };
        if window_id != settings_window_id {
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
                if let Some(ref ws) = self.settings_window {
                    ws.gl_window.resize(physical_size);
                }
            }
            _ => {}
        }

        // Forward event to egui for input handling
        if let Some(ref mut ws) = self.settings_window {
            let event_response = ws
                .egui_glow
                .on_window_event(ws.gl_window.window(), &event);

            if event_response.repaint {
                ws.gl_window.window().request_redraw();
            }

            // Render on RedrawRequested or after input events that need repaint
            if matches!(event, WindowEvent::RedrawRequested) || event_response.repaint {
                let action = ws.render();
                match action {
                    SettingsAction::Close => {
                        self.hide_settings_window();
                    }
                    SettingsAction::Save { port, autostart } => {
                        log!(
                            "settings: saving port={}, autostart={}",
                            port,
                            autostart
                        );
                        let settings = serde_json::json!({
                            "port": port,
                            "autostart": autostart,
                        });
                        if let Ok(data) = serde_json::to_string_pretty(&settings) {
                            let _ = std::fs::write(&ws.settings_path, data);
                        }
                        // Update app state
                        {
                            let mut s = self.state.lock().unwrap();
                            s.port = port;
                            s.autostart = autostart;
                        }
                        if autostart {
                            enable_autostart();
                        } else {
                            disable_autostart();
                        }
                        self.hide_settings_window();
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
        log!("exiting: cleaning up");
        if let Some(ref mut ws) = self.settings_window {
            ws.egui_glow.destroy();
        }
    }
}

// ── App methods ───────────────────────────────────────────────────────────

impl App {
    fn open_settings_window(&mut self, event_loop: &ActiveEventLoop) {
        if self.settings_window.is_none() {
            log!("open_settings_window: creating new window");
            let port = { self.state.lock().unwrap().port };
            let autostart = { self.state.lock().unwrap().autostart };
            let settings_path = self.exe_dir.join("dashboard-settings.json");
            self.settings_window = Some(WindowState::new(
                event_loop,
                port,
                autostart,
                settings_path,
            ));
        }

        if let Some(ref mut ws) = self.settings_window {
            // Update port/autostart from current state
            let s = self.state.lock().unwrap();
            ws.port = s.port;
            ws.autostart = s.autostart;
            drop(s);

            // Render first frame BEFORE showing, so user doesn't see white flash
            log!("open_settings_window: rendering first frame...");
            ws.render();
            ws.gl_window.window().set_visible(true);
            ws.gl_window.window().request_redraw();
            log!("open_settings_window: window visible, redraw requested");
        }
    }

    fn hide_settings_window(&mut self) {
        if let Some(ref ws) = self.settings_window {
            ws.gl_window.window().set_visible(false);
            log!("hide_settings_window: window hidden");
        }
    }

    fn rebuild_menu(&mut self, running: bool, paused: bool) {
        if let (Some(ref items), Some(ref mut tray_icon)) =
            (&self.menu_items, &mut self.tray_icon)
        {
            let menu = tray::build_menu(items, running, paused);
            tray_icon.set_menu(Some(Box::new(menu)));
        }
    }

    fn handle_menu_event(&mut self, event_loop: &ActiveEventLoop, event: tray_icon::menu::MenuEvent) {
        let port = { self.state.lock().unwrap().port };
        let url = format!("http://localhost:{}", port);

        let ids = match &self.menu_ids {
            Some(ids) => ids.clone(),
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

        if *id == ids.open_dashboard {
            log!("menu: open_dashboard");
            let _ = open::that(&url);
        } else if *id == ids.add_project {
            log!("menu: add_project");
            let _ = open::that(format!("{}/setup", url));
        } else if *id == ids.settings {
            log!("menu: settings -> open_settings_window");
            self.open_settings_window(event_loop);
        } else if *id == ids.pause {
            log!("menu: pause");
            let _ =
                ureq::post(&format!("{}/api/control/pause", url)).send_empty();
            // Optimistic state update + menu rebuild
            {
                let mut s = self.state.lock().unwrap();
                s.loop_running = true;
                s.loop_paused = true;
            }
            self.rebuild_menu(true, true);
        } else if *id == ids.resume {
            log!("menu: resume");
            let _ = ureq::delete(&format!("{}/api/control/pause", url)).call();
            {
                let mut s = self.state.lock().unwrap();
                s.loop_running = true;
                s.loop_paused = false;
            }
            self.rebuild_menu(true, false);
        } else if *id == ids.stop_loop {
            log!("menu: stop_loop");
            let _ =
                ureq::post(&format!("{}/api/control/stop", url)).send_empty();
            {
                let mut s = self.state.lock().unwrap();
                s.loop_running = false;
                s.loop_paused = false;
            }
            self.rebuild_menu(false, false);
        } else if *id == ids.start_loop {
            log!("menu: start_loop");
            let _ =
                ureq::post(&format!("{}/api/control/start", url)).send_empty();
            {
                let mut s = self.state.lock().unwrap();
                s.loop_running = true;
                s.loop_paused = false;
            }
            self.rebuild_menu(true, false);
        } else if *id == ids.quit {
            log!("menu: QUIT -> calling std::process::exit(0)");
            std::process::exit(0);
        } else {
            // Check project items
            let mut handled = false;
            for p in &items.projects {
                if *id == p.id {
                    log!("menu: project clicked: {}", p.name);
                    let encoded = p.root.replace('\\', "/").replace(':', "%3A");
                    let _ = open::that(format!("{}/?project={}", url, encoded));
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

    // 检测 --test 模式
    let test_mode = std::env::args().any(|a| a == "--test");
    if test_mode {
        log!("main: TEST MODE enabled");
    }

    let config = Config::load(&exe_dir);
    let port = find_available_port(config.port);
    log!(
        "main: config loaded, port={}, autostart={}",
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
    }));

    if config.autostart {
        enable_autostart();
    }

    let server = Arc::new(Mutex::new(Server::new()));
    let python_exe = Arc::new(find_python(&exe_dir));
    let app_dir = Arc::new(exe_dir.to_string_lossy().to_string());

    log!("main: python_exe={}, app_dir={}", *python_exe, *app_dir);

    log!("main: starting server on port {}", port);
    if !server.lock().unwrap().start(port, &python_exe, &app_dir) {
        log!("main: FAILED to start server");
    }

    let _ = open::that(format!("http://localhost:{}", port));
    log!("main: opened browser at port {}", port);

    // Build event loop with user events
    let event_loop = EventLoop::<UserEvent>::with_user_event()
        .build()
        .unwrap();
    let proxy = event_loop.create_proxy();

    // Register MenuEvent handler — forwards to EventLoopProxy
    MenuEvent::set_event_handler(Some(move |event: tray_icon::menu::MenuEvent| {
        let _ = proxy.send_event(UserEvent::MenuEvent(event));
    }));
    log!("main: MenuEvent handler registered");

    let mut app = App {
        tray_icon: None,
        menu_items: None,
        menu_ids: None,
        settings_window: None,
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
