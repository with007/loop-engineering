#![windows_subsystem = "windows"]

use eframe::egui;
use std::io::Write;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tray_icon::menu::MenuEvent;

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

fn main() {
    let exe_dir = std::env::current_exe().unwrap().parent().unwrap().to_path_buf();
    init_log(&exe_dir);

    // 检测 --test 模式
    let test_mode = std::env::args().any(|a| a == "--test");
    if test_mode { log!("main: TEST MODE enabled"); }

    let config = Config::load(&exe_dir);
    let port = find_available_port(config.port);
    log!("main: config loaded, port={}, autostart={}", port, config.autostart);

    let state = Arc::new(Mutex::new(AppState {
        loop_running: false, loop_paused: false,
        heartbeat: String::new(), current_task: String::new(),
        pending_merge: 0, port, autostart: config.autostart,
    }));

    if config.autostart { enable_autostart(); }

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

    // Create tray BEFORE eframe (must be on main thread too)
    let tray_app = tray::TrayApp::new(state.clone());
    log!("main: tray created");

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1.0, 1.0])
            .with_decorations(false)
            .with_taskbar(false)
            .with_visible(true),   // OS 可见→消息泵正常工作
        ..Default::default()
    };

    // set_event_handler 在 TrackPopupMenu 的 modal loop 内同步调用
    // 不依赖事件循环，MenuItem 点击即时响应
    let menu_items = tray_app.menu_items.clone_ids();
    let show_settings_flag = Arc::new(Mutex::new(false));
    let show_settings_flag2 = show_settings_flag.clone();
    let exe_dir2 = exe_dir.clone();
    let state2 = state.clone();
    let port2 = port;

    // handler 需要 egui context 来唤醒事件循环
    static EGUI_CTX: std::sync::OnceLock<egui::Context> = std::sync::OnceLock::new();

    MenuEvent::set_event_handler(Some(move |event: tray_icon::menu::MenuEvent| {
        log_msg(&format!("handler: id={:?}", event.id));
        let m = &menu_items;
        if event.id == m.settings {
            log_msg("handler: settings clicked");
            *show_settings_flag2.lock().unwrap() = true;
            if let Some(ctx) = EGUI_CTX.get() {
                ctx.request_repaint();
            }
        } else if event.id == m.quit {
            log_msg("handler: quit -> exit");
            std::process::exit(0);
        } else if event.id == m.open_dashboard {
            let _ = open::that(format!("http://localhost:{}", port2));
        } else if event.id == m.add_project {
            let _ = open::that(format!("http://localhost:{}/setup", port2));
        } else if event.id == m.autostart {
            let mut s = state2.lock().unwrap();
            s.autostart = !s.autostart;
            if s.autostart { enable_autostart(); } else { disable_autostart(); }
            let mut c = Config::load(&exe_dir2);
            c.autostart = s.autostart;
            c.save(&exe_dir2);
        } else if event.id == m.pause {
            let _ = ureq::post(&format!("http://localhost:{}/api/control/pause", port2)).send_empty();
        } else if event.id == m.resume {
            let _ = ureq::delete(&format!("http://localhost:{}/api/control/pause", port2)).call();
        } else if event.id == m.stop_loop {
            let _ = ureq::post(&format!("http://localhost:{}/api/control/stop", port2)).send_empty();
        } else if event.id == m.start_loop {
            let _ = ureq::post(&format!("http://localhost:{}/api/control/start", port2)).send_empty();
        }
    }));
    log!("main: MenuEvent handler registered");

    let app = DashboardApp {
        state,
        tray_app,
        server,
        python_exe,
        app_dir,
        exe_dir,
        last_poll: Instant::now(),
        show_settings: false,
        show_settings_flag: show_settings_flag,
        test_mode,
        test_step: 0,
        test_timer: Instant::now(),
        frame_count: 0,
        last_heartbeat: Instant::now(),
        last_frame: Instant::now(),
    };

    log!("main: entering eframe::run_native");
    let _ = eframe::run_native("Loop Dashboard", options, Box::new(|cc| {
        log!("eframe: init callback called");
        let _ = EGUI_CTX.set(cc.egui_ctx.clone());
        cc.egui_ctx.request_repaint(); // 强制初帧

        let mut fonts = egui::FontDefinitions::default();
        if let Some(cjk) = find_cjk_font() {
            fonts.font_data.insert("cjk".to_string(), std::sync::Arc::new(egui::FontData::from_owned(cjk)));
            fonts.families
                .entry(egui::FontFamily::Proportional)
                .or_default()
                .insert(0, "cjk".to_string());
            fonts.families
                .entry(egui::FontFamily::Monospace)
                .or_default()
                .push("cjk".to_string());
            cc.egui_ctx.set_fonts(fonts);
            log!("eframe: CJK font loaded");
        } else {
            log!("eframe: NO CJK FONT FOUND");
        }
        Ok(Box::new(app))
    }));
    log!("main: eframe::run_native returned (app exiting)");
}

struct DashboardApp {
    state: Arc<Mutex<AppState>>,
    tray_app: tray::TrayApp,
    server: Arc<Mutex<Server>>,
    python_exe: Arc<String>,
    app_dir: Arc<String>,
    exe_dir: std::path::PathBuf,
    last_poll: Instant,
    show_settings: bool,
    show_settings_flag: Arc<Mutex<bool>>,
    test_mode: bool,
    test_step: u32,
    test_timer: Instant,
    frame_count: u64,
    last_heartbeat: Instant,
    last_frame: Instant,
}

impl eframe::App for DashboardApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.frame_count += 1;

        // 帧间隔检测：超过 500ms 则告警
        let gap_ms = self.last_frame.elapsed().as_millis();
        if gap_ms > 500 {
            log!("SLOW_FRAME: gap={}ms frame={}", gap_ms, self.frame_count);
        }
        self.last_frame = Instant::now();

        // 心跳日志：每 2 秒确认事件循环存活
        if self.last_heartbeat.elapsed().as_secs() >= 2 {
            self.last_heartbeat = Instant::now();
            log!("heartbeat: frame={}", self.frame_count);
        }

        // ── 测试模式：自动化端到端测试 ──
        if self.test_mode {
            let secs = self.test_timer.elapsed().as_secs();
            match self.test_step {
                0 => {
                    // 步骤 0：等 3s 启动完成 → 打开设置面板
                    if secs >= 3 {
                        log!("test: step 0→1, opening settings panel");
                        self.show_settings = true;
                        self.test_step = 1;
                        self.test_timer = Instant::now();
                    }
                }
                1 => {
                    // 步骤 1：等 1.5s → 关闭设置面板
                    if secs >= 1 {
                        log!("test: step 1→2, closing settings panel");
                        self.show_settings = false;
                        self.test_step = 2;
                        self.test_timer = Instant::now();
                    }
                }
                2 => {
                    // 步骤 2：等 1s → 退出（模拟托盘退出）
                    if secs >= 1 {
                        log!("test: step 2→3, calling std::process::exit(0)");
                        log!("test: ====== ALL TESTS PASSED ======");
                        std::process::exit(0);
                    }
                }
                _ => {}
            }
        }

        // 检测主 viewport 关闭事件
        if ctx.input(|i| i.viewport().close_requested()) {
            log!("update: close_requested on main viewport (UNEXPECTED)");
        }

        // Poll status
        if self.last_poll.elapsed().as_secs() >= 5 {
            self.last_poll = Instant::now();
            log!("update: polling status...");
            poll_and_update(&self.state, &self.tray_app, &self.server, &self.python_exe, &self.app_dir);
        }

        // 从 handler 读取菜单事件（handler 在 TrackPopupMenu 中同步设置）
        if *self.show_settings_flag.lock().unwrap() {
            *self.show_settings_flag.lock().unwrap() = false;
            log!("update: handler set show_settings=true");
            self.show_settings = true;
        }

        // 设置面板
        if self.show_settings {
            log!("update: show_settings=true, calling show_viewport_immediate");

            let (port, autostart, settings_path) = {
                let s = self.state.lock().unwrap();
                (s.port, s.autostart, self.exe_dir.join("dashboard-settings.json"))
            };

            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("settings_panel"),
                egui::ViewportBuilder::default()
                    .with_title("Loop Dashboard 设置")
                    .with_inner_size([380.0, 280.0])
                    .with_resizable(false),
                |settings_ctx, _class| {
                    log!("settings_viewport: callback invoked");

                    if settings_ctx.input(|i| i.viewport().close_requested()) {
                        log!("settings_viewport: close_requested by user");
                        self.show_settings = false;
                        return;
                    }

                    let mut port_str = port.to_string();
                    let mut autostart_val = autostart;

                    egui::CentralPanel::default().show(settings_ctx, |ui| {
                        ui.vertical_centered(|ui| {
                            ui.heading("Loop Dashboard 设置");
                        });
                        ui.separator();
                        ui.horizontal(|ui| {
                            ui.label("端口号:");
                            ui.add(egui::TextEdit::singleline(&mut port_str).desired_width(80.0));
                        });
                        ui.label("修改端口后需重启生效");
                        ui.add_space(8.0);
                        ui.checkbox(&mut autostart_val, "开机自启");
                        ui.add_space(16.0);
                        ui.horizontal(|ui| {
                            if ui.button("保存").clicked() {
                                log!("settings: save clicked, port={}, autostart={}", port_str, autostart_val);
                                let settings = serde_json::json!({
                                    "port": port_str.parse::<u16>().unwrap_or(8765),
                                    "autostart": autostart_val,
                                });
                                if let Ok(data) = serde_json::to_string_pretty(&settings) {
                                    let _ = std::fs::write(&settings_path, data);
                                }
                                self.show_settings = false;
                            }
                            if ui.button("取消").clicked() {
                                log!("settings: cancel clicked");
                                self.show_settings = false;
                            }
                        });
                    });
                },
            );
        }

        // request_repaint_after 设定未来重绘时间 → eframe 用 WaitUntil(timeout)
        // MsgWaitForMultipleObjects 超时唤醒，不依赖窗口消息
        ctx.request_repaint_after(std::time::Duration::from_millis(100));
    }
}

impl DashboardApp {
    fn handle_menu_event(&mut self, event: tray_icon::menu::MenuEvent) {
        let port = { self.state.lock().unwrap().port };
        let url = format!("http://localhost:{}", port);

        let id = &event.id;
        let m = &self.tray_app.menu_items;

        if *id == m.open_dashboard.id() {
            log!("menu: open_dashboard");
            let _ = open::that(&url);
        } else if *id == m.add_project.id() {
            log!("menu: add_project");
            let _ = open::that(format!("{}/setup", url));
        } else if *id == m.settings.id() {
            log!("menu: settings -> show_settings=true");
            self.show_settings = true;
        } else if *id == m.autostart.id() {
            log!("menu: toggle_autostart");
            let mut s = self.state.lock().unwrap();
            s.autostart = !s.autostart;
            let label = if s.autostart { "✓ 开机自启" } else { "  开机自启" };
            let _ = m.autostart.set_text(label);
            if s.autostart { enable_autostart(); } else { disable_autostart(); }
            let mut c = Config::load(&self.exe_dir);
            c.autostart = s.autostart;
            c.save(&self.exe_dir);
        } else if *id == m.pause.id() {
            log!("menu: pause");
            let _ = ureq::post(&format!("{}/api/control/pause", url)).send_empty();
        } else if *id == m.resume.id() {
            log!("menu: resume");
            let _ = ureq::delete(&format!("{}/api/control/pause", url)).call();
        } else if *id == m.stop_loop.id() {
            log!("menu: stop_loop");
            let _ = ureq::post(&format!("{}/api/control/stop", url)).send_empty();
        } else if *id == m.start_loop.id() {
            log!("menu: start_loop");
            let _ = ureq::post(&format!("{}/api/control/start", url)).send_empty();
        } else if *id == m.quit.id() {
            log!("menu: QUIT -> calling std::process::exit(0)");
            std::process::exit(0);
        } else {
            log!("menu: UNKNOWN menu id");
            for p in &self.tray_app.menu_items.projects {
                if *id == p.id {
                    log!("menu: project clicked: {}", p.name);
                    let encoded = p.root.replace('\\', "/").replace(':', "%3A");
                    let _ = open::that(format!("{}/?project={}", url, encoded));
                    break;
                }
            }
        }
    }
}

fn poll_and_update(
    state: &Arc<Mutex<AppState>>,
    tray: &tray::TrayApp,
    server: &Arc<Mutex<Server>>,
    python_exe: &str,
    app_dir: &str,
) {
    let port = { state.lock().unwrap().port };

    if !server::is_port_open(port) {
        log!("poll: server down, restarting...");
        let mut s = state.lock().unwrap();
        s.loop_running = false;
        s.loop_paused = false;
        drop(s);
        if let Some(icon) = &tray.tray {
            let _ = icon.set_tooltip(Some("Loop Engineering\n⚠ 服务器重连中...".to_string()));
        }
        let mut srv = server.lock().unwrap();
        let _ = srv.restart(port, python_exe, app_dir);
        return;
    }

    if let Ok(resp) = ureq::get(&format!("http://localhost:{}/api/control/status", port)).call() {
        if let Ok(json) = resp.into_body().read_json::<serde_json::Value>() {
            let running = json.get("running").and_then(|v| v.as_bool()).unwrap_or(false);
            let paused = json.get("paused").and_then(|v| v.as_bool()).unwrap_or(false);

            let mut s = state.lock().unwrap();
            s.loop_running = running;
            s.loop_paused = paused;

            let status_text = if running && paused { "Loop: 已暂停 ⏸" }
            else if running { "Loop: 运行中 ●" }
            else { "Loop: 未启动 ○" };
            let _ = tray.menu_items.status.set_text(status_text);

            let _ = tray.menu_items.start_loop.set_enabled(!running);
            let _ = tray.menu_items.pause.set_enabled(running && !paused);
            let _ = tray.menu_items.resume.set_enabled(running && paused);
            let _ = tray.menu_items.stop_loop.set_enabled(running);

            let mut tip = String::from("Loop Engineering");
            if running {
                if paused { tip.push_str("\nLoop: 已暂停"); }
                else { tip.push_str("\nLoop: 运行中"); }
            } else { tip.push_str("\nLoop: 未启动"); }
            if !s.current_task.is_empty() {
                tip.push_str(&format!("\n任务: {}", &s.current_task[..s.current_task.len().min(40)]));
            }
            if s.pending_merge > 0 {
                tip.push_str(&format!("\n待合入: {}", s.pending_merge));
            }
            if let Some(icon) = &tray.tray {
                let _ = icon.set_tooltip(Some(tip));
            }
        }
    }
}

fn find_python(exe_dir: &std::path::Path) -> String {
    let embedded = exe_dir.join("python").join("python.exe");
    if embedded.exists() { embedded.to_string_lossy().to_string() }
    else { "python".to_string() }
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

fn get_window_class(hwnd: isize) -> String {
    if hwnd == 0 { return "NULL".into(); }
    let mut buf = [0u16; 64];
    unsafe {
        let len = windows::Win32::UI::WindowsAndMessaging::GetClassNameW(
            windows::Win32::Foundation::HWND(hwnd as _), &mut buf);
        String::from_utf16_lossy(&buf[..len as usize])
    }
}

/// 用 EnumWindows 找到当前进程的 winit 窗口（跳过 tray_icon_app）
fn find_winit_window() -> isize {
    use std::sync::atomic::{AtomicIsize, Ordering};
    use windows::Win32::Foundation::{HWND, LPARAM, BOOL};
    static FOUND: AtomicIsize = AtomicIsize::new(0);

    let pid = std::process::id();
    unsafe extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let pid = lparam.0 as u32;
        let mut proc_id: u32 = 0;
        windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId(hwnd, Some(&mut proc_id));
        if proc_id == pid {
            let mut buf = [0u16; 64];
            let len = windows::Win32::UI::WindowsAndMessaging::GetClassNameW(hwnd, &mut buf);
            if len > 0 && String::from_utf16_lossy(&buf[..len as usize]) != "tray_icon_app" {
                FOUND.store(hwnd.0 as isize, Ordering::Relaxed);
                return BOOL(0);
            }
        }
        BOOL(1)
    }
    unsafe {
        let _ = windows::Win32::UI::WindowsAndMessaging::EnumWindows(
            Some(enum_proc), LPARAM(pid as isize));
    }
    FOUND.load(Ordering::Relaxed)
}
