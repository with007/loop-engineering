## desktop-settings-window

按需创建/销毁的 egui 设置窗口，通过 OpenGL (egui_glow + glutin) 渲染。

### Requirements

- **REQ-SETTINGS-CREATE**: 收到 ShowSettings 事件时，如果窗口不存在则创建 winit Window + glutin OpenGL 上下文 + egui_glow 渲染器
- **REQ-SETTINGS-UI**: 设置面板包含端口号编辑、开机自启复选框、保存/取消按钮
- **REQ-SETTINGS-SAVE**: 保存按钮将端口和自启配置写入 `dashboard-settings.json`
- **REQ-SETTINGS-CLOSE**: 关闭按钮（X 按钮、取消按钮）隐藏窗口但不销毁渲染上下文，应用继续运行
- **REQ-SETTINGS-REOPEN**: 窗口隐藏后可再次通过托盘菜单打开，复用已有的渲染上下文
- **REQ-SETTINGS-CJK**: 设置面板支持中文字体渲染（CJK 字体加载）
