---
name: verifier-desktop
description: >
  Desktop GUI verification. Builds the Rust desktop app, launches it, tests
  tray menu interaction, settings window rendering, and clean shutdown.
---

# verifier-desktop

验证 Desktop GUI 变更。

## 启动检查

```bash
cargo build --release -p loop-dashboard
```
exit code 0 → 继续。

```bash
taskkill /f /im loop-dashboard.exe 2>nul
```

```bash
# 确认二进制存在
test -f desktop/target/release/loop-dashboard.exe && echo "READY" || echo "BLOCKED"
```
不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪些文件变了（事件循环？托盘菜单？设置窗口？）
2. 匹配合适的验证原语
3. 按顺序执行：先编译 → 再自动化测试 → 最后探测
4. 没有匹配的 → 跑**默认**流程

```bash
# 默认：编译 + 内置测试模式自动验证
cargo build --release -p loop-dashboard
./desktop/target/release/loop-dashboard.exe --test &
sleep 8
cat desktop/target/release/dashboard.log
taskkill /f /im loop-dashboard.exe 2>nul
```

## 可用工具

- `cargo` — Rust 编译
- `taskkill` — Windows 进程管理
- 日志文件 — 所有关键路径都写日志（`#![windows_subsystem = "windows"]` 无 console）

## 验证原语

> **日志路径**：开发构建 `desktop/target/release/dashboard.log`，安装版在 `%LOCALAPPDATA%/LoopDashboard/dashboard.log`。

### 编译检查

```bash
cargo build --release -p loop-dashboard
```
确认 exit code 0，无新增 warning。

适用：所有源码文件变更

### 内置测试模式

应用内置 `--test` 参数，自动执行完整 GUI 生命周期：启动 → 打开设置窗口 → 关闭窗口 → 退出。

```bash
taskkill /f /im loop-dashboard.exe 2>nul
rm -f desktop/target/release/dashboard.log
./desktop/target/release/loop-dashboard.exe --test &
sleep 8
cat desktop/target/release/dashboard.log
taskkill /f /im loop-dashboard.exe 2>nul
```
确认 log 含 `ALL TESTS PASSED` + 关键日志行：
- `main: server ready on port` — 服务启动成功
- `open_settings_window: window visible` — GL 窗口渲染正常
- `hide_settings_window: window hidden` — 窗口关闭正确
- `test: ====== ALL TESTS PASSED ======` — 测试通过

适用：渲染变更、系统初始化变更、事件循环变更、窗口生命周期变更

### 日志驱动验证

不依赖 GUI 交互，读日志确认关键路径全部走到：tray icon 创建、server 启动、polling 心跳。

```bash
taskkill /f /im loop-dashboard.exe 2>nul
rm -f desktop/target/release/dashboard.log
./desktop/target/release/loop-dashboard.exe &
sleep 5
cat desktop/target/release/dashboard.log
# 确认包含：
# - "main: server ready on port" — Python server 启动成功
# - "new_events: tray icon created" — 托盘图标创建成功
# - "heartbeat: poll mode active" — 事件循环正常运行
taskkill /f /im loop-dashboard.exe 2>nul
```

适用：初始化逻辑变更、server 管理变更、非 GUI 模块变更
注意：需要桌面环境（不能 headless）

### 托盘菜单交互验证

用 Windows SendMessage 模拟右键托盘 → 点击菜单项，验证菜单项触发正确逻辑。

```bash
# 此原语依赖 tray icon 的 Windows 消息机制
# 具体实现依赖项目 .claude/scripts/ 下的测试脚本（如有）
# 若无自动化脚本 → 改为人工验证清单
```

适用：托盘菜单结构变更、菜单项增删、per-project 动态菜单变更
注意：若项目无自动化菜单测试脚本 → 跳过此项，改人工验证

## 探测

**托盘类应用**：
- 关闭窗口 → 不应退出（只隐藏，托盘图标仍在）
  - 操作：打开设置窗口 → 点 X 关闭 → 检查进程仍存活
- 右键托盘 → 菜单正确弹出，标签正确
- 托盘退出 → 进程干净终止（无僵尸进程，端口释放）
  ```bash
  taskkill /f /im loop-dashboard.exe 2>nul
  # 确认端口释放
  netstat -ano | findstr ":8765" || echo "port released OK"
  ```
- 重复打开/关闭窗口 → 无空白窗口、无 crash
  - 操作：连续多次右键 → 设置 → 点 X 关闭，检查日志无报错

**项目特有**：
- 首次运行（无 `dashboard-settings.json`）→ 应自动弹出设置窗口
  ```bash
  rm -f desktop/target/release/dashboard-settings.json
  ./desktop/target/release/loop-dashboard.exe &
  sleep 4
  cat desktop/target/release/dashboard.log | grep "first run"
  taskkill /f /im loop-dashboard.exe 2>nul
  ```
- Server 端口被占 → 应自动 +1 重试（最多 5 次）
- Python 子进程崩溃 → 后台轮询应自动重启 server

## 清理

```bash
taskkill /f /im loop-dashboard.exe 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*" 2>nul
```
确认无残留进程，端口释放。

## 自更新

- 二进制名变了 → 更新上方命令
- 新增托盘菜单项 → 补充到探测
- 构建系统换了 → 更新编译命令
- 日志路径或文件名变了 → 更新所有 cat 路径
- 新增 UserEvent 类型 → 补充到日志驱动验证的关键日志行
- --test 模式的测试步骤变了 → 更新内置测试模式原语
