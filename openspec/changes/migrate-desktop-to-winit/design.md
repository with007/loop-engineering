## Architecture

```
EventLoop::with_user_event<UserEvent>()
│
├── event_loop.set_control_flow(ControlFlow::Poll)  ← 关键: 恒定 60Hz
│
├── ApplicationHandler::new_events(Init)
│   └── 创建 TrayIcon + 注册 MenuEvent::set_event_handler
│
├── ApplicationHandler::user_event(MenuEvent)
│   ├── ShowSettings → create_window() (按需创建 egui 窗口)
│   ├── OpenDashboard → open::that(url)
│   ├── API calls → ureq HTTP
│   └── Quit → std::process::exit(0)
│
├── ApplicationHandler::window_event(RedrawRequested)
│   └── egui_glow 渲染 → glutin swap_buffers
│
├── ApplicationHandler::window_event(CloseRequested)
│   └── 关闭设置窗口，设置 Option<WindowState> = None，不退出
│
└── 轮询循环 (10s 一次服务器状态检查)
```

## Reference Code

### 1. tray-icon/examples/winit.rs — 纯托盘 + winit 事件循环

本地路径: `~/.cargo/registry/.../tray-icon-0.19.3/examples/winit.rs`

关键模式:
- `EventLoop::with_user_event<UserEvent>()` 创建带自定义事件的循环
- `MenuEvent::set_event_handler` 转发菜单事件到 `EventLoopProxy`
- 托盘在 `new_events(StartCause::Init)` 创建（事件循环启动后第一帧）
- 不创建任何 winit Window，纯托盘应用

### 2. egui_glow/examples/pure_glow.rs — egui + winit 直接集成

本地路径: `~/.cargo/registry/.../egui_glow-0.31.1/examples/pure_glow.rs`

关键模式:
- `ApplicationHandler` trait 实现完整事件循环
- `glutin` + `glutin-winit` 创建 OpenGL 上下文
- `ControlFlow::Poll` / `WaitUntil` / `Wait` 动态切换（根据是否需要重绘）
- `window_event(CloseRequested|Destroyed)` → `event_loop.exit()`
- `window_event(RedrawRequested)` → 调用 egui_glow 渲染管线

## Implementation

### 依赖变更

```toml
# 移除
eframe = "0.31"
egui = "0.31"

# 新增
winit = "0.30"
egui_glow = "0.31"
egui_winit = "0.31"
glutin = "*"
glutin-winit = "*"
glow = "*"

# 保留
tray-icon = "0.19"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_yaml = "0.9"
auto-launch = "0.5"
ureq = { version = "3", features = ["json"] }
open = "5"
dirs = "6"
log = "0.4"
env_logger = "0.11"
windows = { version = "0.58", features = [...] }
```

### 数据结构

```rust
enum UserEvent {
    MenuEvent(tray_icon::menu::MenuEvent),
    ShowSettings,
}

struct App {
    tray_icon: Option<TrayIcon>,
    settings_window: Option<WindowState>,
    server: Arc<Mutex<Server>>,
    state: Arc<Mutex<AppState>>,
    // ... config, paths, etc.
}

struct WindowState {
    window: winit::window::Window,
    egui_glow: egui_glow::EguiGlow,
    gl_window: GlutinWindowContext,  // from pure_glow pattern
    show: bool,
    port: u16,
    autostart: bool,
    settings_path: PathBuf,
}
```

### 设置窗口生命周期

```
托盘点击"设置" → user_event(ShowSettings)
  → 如果 settings_window 为 None → 创建 Window + GlutinWindowContext + EguiGlow
  → window.set_visible(true)
  → show = true

Render loop:
  → RedrawRequested → egui_glow.run(window, |ctx| { settings_ui })
  → "保存"/"取消" → window.set_visible(false), show = false
  → CloseRequested → window.set_visible(false), show = false
  → 不销毁 window（保留 GlutinWindowContext 可复用）
```

### 事件循环模式

```rust
impl ApplicationHandler<UserEvent> for App {
    fn new_events(&mut self, _event_loop: &ActiveEventLoop, cause: StartCause) {
        if cause == StartCause::Init {
            // 创建托盘图标
            self.tray_icon = Some(create_tray());
        }
        // 设置 Poll 模式（Init 后每帧都来）
        _event_loop.set_control_flow(ControlFlow::Poll);
        
        // 轮询服务器状态（10s 一次）
        if self.last_poll.elapsed() > Duration::from_secs(10) {
            poll_and_update(...);
        }
    }

    fn user_event(&mut self, _event_loop: &ActiveEventLoop, event: UserEvent) {
        match event {
            UserEvent::MenuEvent(e) => handle_menu(e),
            UserEvent::ShowSettings => { /* 创建/显示窗口 */ }
        }
    }

    fn window_event(&mut self, event_loop: &ActiveEventLoop, _id: WindowId, event: WindowEvent) {
        match event {
            WindowEvent::CloseRequested => {
                // 隐藏设置窗口，不退出
                if let Some(ws) = &self.settings_window {
                    ws.window.set_visible(false);
                    ws.show = false;
                }
            }
            WindowEvent::RedrawRequested => {
                // egui 渲染
                self.settings_window.as_mut().unwrap().render();
            }
            _ => {}
        }
    }
}
```

### 与当前代码的复用

| 模块 | 复用程度 |
|------|---------|
| `tray.rs` → `create_tray()` 函数 | 几乎全复用，去掉 `Arc<Mutex<TrayApp>>` 包装 |
| `server.rs` | 完全复用 |
| `config.rs` | 完全复用 |
| `main.rs` 设置 UI | 内联到 `WindowState::render()` |
| `main.rs` handle_menu_event | 内联到 `handle_menu()` |
| `main.rs` poll_and_update | 完全复用 |
| 日志系统 | 完全复用 |
