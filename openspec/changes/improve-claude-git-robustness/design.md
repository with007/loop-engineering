## Context

参考 claude-controller 项目的成熟实现，在不改变 loop-engineering 现有架构的前提下，补上环境隔离、进程启动可靠性、git 容错、测试基础设施四个防御性缺口。

## Decisions

### 1. 环境变量清理 — 在 `start_loop` 中处理

**选择**：在 `control.py:start_loop` 的 `subprocess.Popen` 前，从 `os.environ.copy()` 中 pop 掉 `CLAUDECODE` 和 `CLAUDE_CODE_ENTRYPOINT`，通过 `env` 参数传入。

**原因**：`start_loop` 是唯一直接 spawn Claude Code 进程的地方。setup.py 的 `_run` 调用的是 git/shell 命令，不需要清理 Claude 环境变量。

**不选**：全局修改 `os.environ` — 会影响当前进程和所有后续子进程，副作用太大。

### 2. Claude 路径解析 — `shutil.which`

**选择**：在 `start_loop` 生成 .bat 前，用 `shutil.which("claude")` 查找实际路径。如果找不到，再尝试 `shutil.which("claude.cmd")`。找到后写入 .bat 的绝对路径。

**原因**：避免依赖 `PATHEXT` 隐式解析，确保在各种 Windows 环境下都能找到可执行文件。

### 3. Git utils 模块 — 新文件 `git_utils.py`

**选择**：新建 `src/loop_engineering/git_utils.py`，提供：
- `fetch_with_retry(repo_path, remote="origin", retries=3)` — 异步不强制，封装同步 subprocess + 指数退避
- `is_fetch_available(repo_path)` — 快速检测网络可达性
- `branch_to_dirname(branch)` — 从 claude-controller 移植（当前 LE 不需要但作为工具函数保留）

**调用方**：`setup.py` 的 `_create_single_worktree` 和 `sync_to_agent` 改用 `fetch_with_retry`。

### 4. 离线模式 — setup.py 显式降级

**选择**：`_create_single_worktree` 中 `git fetch origin` 改为调用 `fetch_with_retry`。如果最终仍失败：
- 检查本地是否有可用的 default ref（master/main）
- 有 → 打印 `[OFFLINE] 使用本地分支`，继续 worktree add
- 没有 → 抛出明确错误 `"无法连接远程且本地无可用分支"`

**与现状的区别**：现状是 fetch 失败静默忽略，碰巧能用但不透明。改造后明确告知用户当前处于离线模式。

### 5. pytest 测试基础设施

**选择**：
- `pyproject.toml` 添加 `[project.optional-dependencies]` 的 `test` 组（pytest）
- `tests/` 目录下建立测试文件，每个核心脚本对应一个 test 文件
- Mock 方式：使用 `tmp_path` fixture 创建临时 tasks.md / loop-config.yaml，调用脚本函数验证输出
- 测试数据：内联在测试文件中，不依赖外部文件

**覆盖范围**：
| 测试文件 | 覆盖脚本 | 关键场景 |
|-----------|----------|----------|
| `tests/test_task_pick.py` | task_pick.py | 分配匹配、跳过已有远程分支、无任务返回 NONE |
| `tests/test_task_done.py` | task_done.py | tasks.md 状态更新、runlog 写入 |
| `tests/test_task_cleanup.py` | task_cleanup.py | 合入检测、分支清理 |
| `tests/test_config.py` | config.py | 深度合并、None 删除、类型转换 |

## Risks / Trade-offs

- **离线模式**：如果用户本地 master 很旧，离线 worktree 会是旧代码。但比 outright 失败强，用户后续手动 `git fetch` 即可。
- **pytest**：测试用 mock 数据，不覆盖真实 git 操作和 Claude 进程交互。这些仍需手动或集成测试验证（符合 CLAUDE.md 的"真实环境"原则）。
