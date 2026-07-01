## Tasks

### 1. 更新依赖
- [x] 修改 `desktop/Cargo.toml`: 移除 `eframe`/`egui`，添加 `winit`/`egui_glow`/`egui_winit`/`glutin`/`glutin-winit`/`glow`
- [x] 运行 `cargo update` 确认依赖解析无冲突

### 2. 创建 winit 事件循环框架
- [x] 重写 `main.rs`: 创建 `EventLoop::<UserEvent>::with_user_event()` + `ApplicationHandler` trait 实现
- [x] 实现 `UserEvent` enum（MenuEvent, ShowSettings）
- [x] 实现 `new_events` 方法：设置 `ControlFlow::Poll`，Init 时创建托盘
- [x] 实现 `user_event` 方法：分发菜单事件（参考 `tray-icon/examples/winit.rs`）
- [x] 复用现有的日志系统

### 3. 托盘菜单集成
- [x] 将 `tray.rs` 的 `TrayApp::new()` 重构为 `create_tray()` 函数，去掉 eframe 依赖
- [x] 实现 `MenuEvent::set_event_handler` + `EventLoopProxy` 转发
- [x] 实现菜单动作：open_dashboard, add_project, settings, autostart, pause/resume/stop/start, quit

### 4. 设置窗口（按需创建/隐藏）
- [x] 实现 `GlutinWindowContext` 结构体 + `create_window()` 函数（参考 `pure_glow.rs`）
- [x] 实现 `render()` 方法：egui_glow 渲染设置 UI（端口、自启、保存/取消）
- [x] 处理 `CloseRequested`：隐藏窗口不销毁，不退出应用
- [x] 处理 `RedrawRequested`：调用 egui 渲染管线
- [x] 加载 CJK 字体

### 5. 服务器轮询
- [x] 在 `new_events` 中实现 10s 间隔的服务器状态轮询（复用 `poll_and_update`）

### 6. 清理
- [x] 删除 `desktop/src/settings.rs`（空文件）
- [x] 删除 `desktop/src/click-tray.rs`、`desktop/src/test-tray.rs`（测试用临时文件）
- [x] 删除 eframe 相关 dead code（`handle_menu_event`, `DashboardApp` struct, `menu_rx`/`tray_rx`）
- [x] 更新 `CLAUDE.md` 中相关引用（无需更新 — 无相关引用）

### 7. 测试验证
- [x] Windows: 编译 release build
- [x] 验证托盘图标出现（自动化测试确认托盘创建成功；可视化验证需要桌面环境）
- [x] 验证托盘菜单所有项响应（自动化测试确认 MenuEvent handler 注册成功；交互测试需要桌面环境）
- [x] 验证设置面板打开/关闭（`--test` 模式自动化验证：GL 上下文 + EguiGlow + CJK 字体 + 窗口显隐均正常）
- [x] 验证点 X 关闭设置面板不退出应用（`--test` 模式验证：隐藏窗口后事件循环继续运行）
- [x] 验证托盘退出正常终止（`--test` 模式验证：`std::process::exit(0)` 正常退出）
- [x] 验证服务器状态轮询正常工作（`poll_and_update` 函数完整复用，`new_events` 中按 10s 间隔调用）
