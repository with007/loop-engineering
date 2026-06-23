## test-infra

pytest 自动化测试框架，覆盖核心脚本的纯逻辑部分。

### Requirements

#### TEST-001: pytest 项目配置

- `pyproject.toml` 的 `[project.optional-dependencies]` 添加 `test` 组，包含 `pytest>=7.0`
- `[tool.pytest.ini_options]` 配置 `testpaths = ["tests"]`
- `tests/` 目录下创建 `__init__.py`（空文件）和 `conftest.py`（共享 fixtures）

#### TEST-002: task_pick 测试

`tests/test_task_pick.py`：
- `test_picks_assigned_task`：tasks.md 中有 `[ ] task1 (→ with)`，输出 `taskID=... desc=task1`
- `test_skips_remote_branch`：任务已有 `origin/agent/with/task1` 远程分支时跳过
- `test_no_tasks_returns_none`：无匹配任务时输出 `NONE`
- `test_skips_done_tasks`：`[x]` 和 `[~]` 状态的任务不被选中

#### TEST-003: task_done 测试

`tests/test_task_done.py`：
- `test_updates_tasks_md`：`[ ]` / `[~]` → `[x]`，追加时间戳和 IMP/VFY 记录
- `test_writes_run_log`：调用后 `.loop-engineering/runs/` 下生成对应 JSON 文件

#### TEST-004: task_cleanup 测试

`tests/test_task_cleanup.py`：
- `test_detects_merged_branch`：已合入 master 的分支被识别
- `test_skips_unmerged_branch`：未合入的分支不被清理

#### TEST-005: config 测试

`tests/test_config.py`：
- `test_merge_adds_new_key`
- `test_merge_none_deletes_key`
- `test_merge_overwrites_value`
- `test_merge_nested_keys`

### Acceptance

- [ ] `pytest` 命令能发现并运行所有测试
- [ ] 所有测试通过（mock 环境，不需要真实 git/claude）
- [ ] 每个测试独立，不依赖其他测试的执行顺序
