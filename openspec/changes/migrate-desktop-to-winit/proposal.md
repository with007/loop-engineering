## Why

桌面托盘应用（`desktop/`）使用 eframe 框架时，隐藏窗口后 `ControlFlow::Wait` 导致事件循环停摆：无系统消息就永不休眠唤醒，托盘菜单事件无法被 `try_recv()` 轮询到，设置面板也无法通过 `show_viewport_immediate` 打开。eframe 封装了 `ControlFlow` 不允许外部修改。需要迁移到 winit 直接控制事件循环，使用 `ControlFlow::Poll` 模式。

## What Changes

- **BREAKING**: 移除 `eframe` 依赖，换为 `winit` + `egui_glow` + `glutin` + `egui_winit` 直接控制
- 事件循环从 `eframe::run_native` 改为 `winit::EventLoop` + `ApplicationHandler` trait
- `ControlFlow::Poll` 确保无论窗口可见与否，事件循环恒定 60Hz 运行
- 设置面板从 `show_viewport_immediate`（eframe 多 viewport）改为按需创建 winit Window + egui_glow 渲染
- 菜单事件通过 `MenuEvent::set_event_handler` + `EventLoopProxy` 转发，不依赖通道轮询
- 托盘、服务器管理、配置模块复用（tray.rs, server.rs, config.rs 基本不动）

## Capabilities

### New Capabilities

- `desktop-winit-eventloop`: 基于 winit ApplicationHandler 的事件循环，Poll 模式持续运行，托盘事件即时响应
- `desktop-settings-window`: 按需创建/销毁的 egui 设置窗口，通过 OpenGL (egui_glow + glutin) 渲染

### Modified Capabilities

<!-- 无现有 capability 需要修改 -->

## Impact

- `desktop/Cargo.toml`: 替换 eframe/egui 依赖为 winit + egui_glow + glutin + egui_winit
- `desktop/src/main.rs`: 重写事件循环（~300 行改为 ApplicationHandler 模式）
- `desktop/src/tray.rs`: 不变（托盘创建逻辑复用）
- `desktop/src/server.rs`: 不变
- `desktop/src/config.rs`: 不变
- 移除 `desktop/src/settings.rs`（设置 UI 内联到 main.rs 的窗口创建逻辑）
- 删除 `MenuEvent::receiver()` 通道轮询相关代码
