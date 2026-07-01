## desktop-winit-eventloop

桌面应用的 winit 事件循环，`ControlFlow::Poll` 模式持续运行，不依赖窗口可见性。

### Requirements

- **REQ-EVENTLOOP-POLL**: 事件循环必须使用 `ControlFlow::Poll`，确保在无可见窗口时仍以 60Hz 运行
- **REQ-EVENTLOOP-TRAY-EVENTS**: 托盘菜单事件通过 `MenuEvent::set_event_handler` + `EventLoopProxy` 转发到事件循环，在 `user_event` 中同步处理
- **REQ-EVENTLOOP-NO-WINDOW**: 事件循环启动时不创建任何窗口，仅创建托盘图标
- **REQ-EVENTLOOP-SERVER-POLL**: 事件循环每 10 秒轮询一次 Python uvicorn 服务器状态
- **REQ-EVENTLOOP-QUIT**: 收到退出菜单事件时调用 `std::process::exit(0)` 立即终止
- **REQ-EVENTLOOP-PLATFORM**: Windows 上使用 `#![windows_subsystem = "windows"]` 隐藏控制台；Linux 上在独立线程中运行 gtk 托盘
