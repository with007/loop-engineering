## 1. git_utils 模块

- [ ] 1.1 新建 `src/loop_engineering/git_utils.py`，实现 `fetch_with_retry`（指数退避重试）、`is_fetch_available`（离线检测）、`branch_to_dirname`（分支名安全转换）

## 2. setup.py 接入 git_utils

- [ ] 2.1 `_create_single_worktree`：`git fetch origin` 替换为 `fetch_with_retry`，重试耗尽后显式降级离线模式（打印 [OFFLINE] 提示，使用本地分支），本地也无可用分支时抛明确错误
- [ ] 2.2 `sync_to_agent` 中的 `git fetch origin` 替换为 `fetch_with_retry`

## 3. env-isolation: 环境变量清理

- [ ] 3.1 `control.py:start_loop` 在 `subprocess.Popen` 前复制环境变量并 pop `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT`，通过 `env=` 传入
- [ ] 3.2 Windows .bat 文件开头添加 `set CLAUDECODE=` / `set CLAUDE_CODE_ENTRYPOINT=`，确保 PS1 路径也覆盖

## 4. env-isolation: Claude 路径解析

- [ ] 4.1 `control.py:start_loop` 用 `shutil.which("claude")` 及 `shutil.which("claude.cmd")` 查找可执行文件绝对路径，写入 .bat；都找不到时抛 `FileNotFoundError`

## 5. pytest 测试基础设施

- [ ] 5.1 `pyproject.toml` 添加 `[project.optional-dependencies]` 的 `test` 组（pytest>=7.0）和 `[tool.pytest.ini_options]`
- [ ] 5.2 创建 `tests/conftest.py`（共享 fixtures）和 `tests/__init__.py`
- [ ] 5.3 创建 `tests/test_task_pick.py`，覆盖：分配匹配、跳过远程分支、无任务返回 NONE、跳过已完成任务
- [ ] 5.4 创建 `tests/test_task_done.py`，覆盖：tasks.md `[ ]`→`[x]`、runlog 写入
- [ ] 5.5 创建 `tests/test_task_cleanup.py`，覆盖：已合入分支识别、未合入分支跳过
- [ ] 5.6 创建 `tests/test_config.py`，覆盖：新增键、None 删除、值覆写、嵌套合并
- [ ] 5.7 `pytest` 全量通过
