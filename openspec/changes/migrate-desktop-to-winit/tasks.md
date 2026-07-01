## Tasks

### 1. 更新依赖
- [ ] 修改 `desktop/Cargo.toml`: 移除 `eframe`/`egui`，添加 `winit`/`egui_glow`/`egui_winit`/`glutin`/`glutin-winit`/`glow`
- [ ] 运行 `cargo update` 确认依赖解析无冲突

### 2. 创建 winit 事件循环框架
- [ ] 重写 `main.rs`: 创建 `EventLoop::<UserEvent>::with_user_event()` + `ApplicationHandler` trait 实现
- [ ] 实现 `UserEvent` enum（MenuEvent, ShowSettings）
- [ ] 实现 `new_events` 方法：设置 `ControlFlow::Poll`，Init 时创建托盘
- [ ] 实现 `user_event` 方法：分发菜单事件（参考 `tray-icon/examples/winit.rs`）
- [ ] 复用现有的日志系统

### 3. 托盘菜单集成
- [ ] 将 `tray.rs` 的 `TrayApp::new()` 重构为 `create_tray()` 函数，去掉 eframe 依赖
- [ ] 实现 `MenuEvent::set_event_handler` + `EventLoopProxy` 转发
- [ ] 实现菜单动作：open_dashboard, add_project, settings, autostart, pause/resume/stop/start, quit

### 4. 设置窗口（按需创建/隐藏）
- [ ] 实现 `GlutinWindowContext` 结构体 + `create_window()` 函数（参考 `pure_glow.rs`）
- [ ] 实现 `render()` 方法：egui_glow 渲染设置 UI（端口、自启、保存/取消）
- [ ] 处理 `CloseRequested`：隐藏窗口不销毁，不退出应用
- [ ] 处理 `RedrawRequested`：调用 egui 渲染管线
- [ ] 加载 CJK 字体

### 5. 服务器轮询
- [ ] 在 `new_events` 中实现 10s 间隔的服务器状态轮询（复用 `poll_and_update`）

### 6. 清理
- [ ] 删除 `desktop/src/settings.rs`（空文件）
- [ ] 删除 `desktop/src/click-tray.rs`、`desktop/src/test-tray.rs`（测试用临时文件）
- [ ] 删除 eframe 相关 dead code（`handle_menu_event`, `DashboardApp` struct, `menu_rx`/`tray_rx`）
- [ ] 更新 `CLAUDE.md` 中相关引用

### 7. 测试验证
- [ ] Windows: 编译 release build
- [ ] 验证托盘图标出现
- [ ] 验证托盘菜单所有项响应
- [ ] 验证设置面板打开/关闭
- [ ] 验证点 X 关闭设置面板不退出应用
- [ ] 验证托盘退出正常终止
- [ ] 验证服务器状态轮询正常工作
