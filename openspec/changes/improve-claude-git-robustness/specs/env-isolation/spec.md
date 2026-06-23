## env-isolation

子进程环境变量隔离，防止 Claude Code 会话嵌套导致的路由异常。

### Requirements

#### ENV-001: Claude 环境变量清理

`start_loop(project_root)` 在启动 Claude Code 子进程前：
- 复制当前进程环境变量 `os.environ.copy()`
- 移除 `CLAUDECODE`（如果存在）
- 移除 `CLAUDE_CODE_ENTRYPOINT`（如果存在）
- 通过 `subprocess.Popen(..., env=cleaned_env)` 传入清理后的环境

注意：只影响 `start_loop` 启动的子进程，不影响当前进程的 `os.environ`。

#### ENV-002: Claude 可执行文件路径解析

`start_loop(project_root)` 在生成 .bat 文件前：
- 调用 `shutil.which("claude")` 查找可执行文件
- 如果未找到，再尝试 `shutil.which("claude.cmd")`
- 如果都未找到，抛出 `FileNotFoundError` 并附带安装说明
- 找到的绝对路径写入 .bat 文件，替代硬编码的 `claude`

#### ENV-003: PS1 心跳脚本也清理环境

Windows 上 `start_loop` 生成的 `loop.ps1` 脚本中，`Start-Process` 启动的 cmd 进程也应继承清理后的环境。通过在 .bat 文件开头添加 `set CLAUDECODE=` 和 `set CLAUDE_CODE_ENTRYPOINT=` 实现。

### Acceptance

- [ ] `start_loop` 启动的子进程不包含 `CLAUDECODE` 环境变量
- [ ] `start_loop` 启动的子进程不包含 `CLAUDE_CODE_ENTRYPOINT` 环境变量
- [ ] 当前进程的 `os.environ` 不变
- [ ] `shutil.which("claude")` 或 `shutil.which("claude.cmd")` 都找不到时抛 `FileNotFoundError`
- [ ] .bat 文件中使用 claude 绝对路径而非 `claude`
