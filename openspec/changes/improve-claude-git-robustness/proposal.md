## Why

参考 [claude-controller](https://github.com/anthropics/claude-code) 项目的成熟实现，loop-engineering 在环境隔离、进程启动可靠性、git 操作容错三个方面存在可改进的防御性缺口。这些改进不改变现有架构，成本低、风险小，能显著减少环境因素导致的 loop 中断。

## What Changes

- **环境变量清理**：启动 Claude Code 子进程前移除 `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT`，防止嵌套 Claude 会话导致路由异常
- **Claude 可执行文件路径解析**：用 `shutil.which` 查找 `claude` + `claude.cmd`，替代 .bat 中硬编码 `claude`
- **Git fetch 重试**：新建 `git_utils.py` 模块，git fetch 失败时指数退避重试（1s/2s/4s，最多 3 次）
- **离线 Git 模式显式支持**：git fetch 失败后不静默忽略，改为显式降级到本地分支并提示用户
- **pytest 测试基础设施**：为核心脚本（task_pick、task_done、task_cleanup、config）建立自动化测试，mock 文件系统即可验证逻辑正确性

## Capabilities

### New Capabilities

- `git-utils`: 统一的 Git 操作工具模块，包含 fetch-with-retry 和离线模式降级逻辑
- `env-isolation`: 子进程环境变量清理，防止 Claude Code 会话嵌套
- `test-infra`: pytest 自动化测试框架，覆盖核心脚本（task_pick、task_done、task_cleanup、config）的逻辑正确性

### Modified Capabilities

（无，现有 spec 为空）

## Impact

- `src/loop_engineering/control.py` — `start_loop` 函数：加 env.pop + claude 路径解析
- `src/loop_engineering/setup.py` — `_create_single_worktree`、`sync_to_agent`：改用 `git_utils.fetch_with_retry`
- 新增 `src/loop_engineering/git_utils.py` — fetch retry、离线检测、分支解析等可复用 git 操作
- `src/loop_engineering/server/templates/control.html` — Dashboard 可能展示离线状态（后续）
- `tests/` — pytest 测试目录，覆盖 task_pick、task_done、task_cleanup、config
- `pyproject.toml` — 添加 pytest 依赖和配置
