## 1. 基础设施 — path-utils + atomic-writes

- [x] 1.1 新建 `src/loop_engineering/path_utils.py`，实现 `find_project_root(start_dir?)`、`resolve_project_root(project?, request?)`、`get_default_branch(repo_path?)`，从 `config.py` 导入 `is_project_dir`
- [x] 1.2 在 `config.py` 新增 `get_agent_dir(config)` 和 `get_data_agent_dir(config)`
- [x] 1.3 新建 `src/loop_engineering/utils.py`，实现 `atomic_write(path, content)`
- [x] 1.4 替换所有 `_project_root` / `_find_project_root` 调用为 `path_utils` 函数（`server/app.py`、`server/api/*.py` × 6、`scripts/*.py` × 3、`cli.py` × 2）
- [x] 1.5 替换所有 `_default_branch` 调用为 `path_utils.get_default_branch`（`setup.py`、`scripts/task_done.py`、`scripts/task_cleanup.py`）
- [x] 1.6 替换所有 `os.path.join(agent_workspace, project_name)` 为 `config.get_agent_dir(config)`（`setup.py` × 11 处）
- [x] 1.7 替换 `config.py:write_config`、`setup.py:_write_json_if_changed`、`runlog.py:write_run_log` 的 `open().write()` 为 `atomic_write()`

## 2. TaskLine — tasks.md 解析统一

- [x] 2.1 在 `task_id.py` 新增 `TaskLine` dataclass（`parse(line) -> TaskLine | None`、`format() -> str`）
- [x] 2.2 改写 `server/app.py:_read_tasks` 使用 `TaskLine.parse`
- [x] 2.3 改写 `server/api/tasks.py:list_tasks` 使用 `TaskLine.parse`（顺带修复 `/api/tasks/add` 不生成 `[task_id]` 的 bug）
- [x] 2.4 改写 `scripts/task_pick.py` 使用 `TaskLine.parse`
- [x] 2.5 改写 `scripts/task_done.py` 使用 `TaskLine.parse` + `TaskLine.format`
- [x] 2.6 删除 `server/app.py` 和 `server/api/tasks.py` 中各自实现的状态过滤重复逻辑，统一到 `services/task_parser.py:filter_tasks()`（补全 order desc/asc、filter_name agent 名筛选、逗号分隔多状态）

## 3. 脚本协议 — --format=shell

- [x] 3.1 在 `scripts/task_pick.py` 新增 `--format` 参数，`--format=shell` 输出 `shlex.quote` 转义的 shell 变量
- [x] 3.2 在 `scripts/task_done.py` 新增 `--format` 参数
- [x] 3.3 在 `scripts/task_cleanup.py` 新增 `--format` 参数
- [x] 3.4 更新 SKILL.md 模板（`templates/skills/task-runner/SKILL.md.j2`，见任务 6.2）中 Step 1 的 task_pick 调用为 `--format=shell` + `eval`

## 4. 测试基础设施

- [x] 4.1 在 `pyproject.toml` 新增 `[project.optional-dependencies] test = ["pytest>=7.0"]`
- [x] 4.2 新建 `tests/conftest.py`（`tmp_path` fixtures）
- [x] 4.3 新建 `tests/test_task_id.py`，覆盖 `generate_task_id`、`make_readable_slug`、`parse_task_id`、`extract_task_id_from_branch`、`make_branch_name`、`TaskLine.parse`、`TaskLine.format`
- [x] 4.4 运行 `python -m pytest` 确认全部通过
- [x] 4.5 新建 `tests/test_config.py`，覆盖 `merge_config` deep_merge（合并/删除/变更跟踪/不修改原值）
- [x] 4.6 新建 `tests/test_control.py`，覆盖 heartbeat write/read/is_running、pause/resume、throttle get/set、get_status
- [x] 4.7 新建 `tests/test_runlog.py`，覆盖 `write_run_log`、`list_runs` 过滤（whoami/result/days）、`get_pass_rate` 计算

## 5. Server 拆分

- [x] 5.1 新建 `server/services/__init__.py`
- [x] 5.2 新建 `server/services/task_parser.py`，提取 `parse_tasks(project_root) -> list[TaskLine]` 和 `filter_tasks(tasks, status, order, filter_name) -> list[TaskLine]`
- [x] 5.3 新建 `server/services/project_context.py`，提取 `build_projects_context(request, current_pr, agent_filter) -> list[dict]`
- [x] 5.4 新建 `server/dependencies.py`，提取 `_project_root`、`_agent_name`、`_render`、`_is_htmx` 共享依赖
- [x] 5.5 新建 `server/routers/__init__.py`
- [x] 5.6 新建 `server/routers/pages.py`（页面路由：/, /tasks, /runs, /control, /settings, /setup，已从 app.py 迁入）
- [x] 5.7 新建 `server/routers/fragments.py`（HTMX 片段路由：/api/projects/switcher, /tasks/list, /tasks/list-items, /tasks/add, /control/status-fragment, /control/info-fragment, /api/setup/browse, /setup/run，已从 app.py 迁入）
- [x] 5.8 精简 `server/app.py` 为 FastAPI 实例 + router 注册 + `start_server()`（所有路由已迁出）
- [x] 5.9 删除 `server/app.py` 中的 `_read_tasks`、`_build_projects_context`、`_filter_agent_workspace_copies`（已迁移到 services）

## 6. 模板分离

- [x] 6.1 新建 `templates/skills/task-runner/SKILL.md.j2`，内容从 `setup.py:SKILL_MD_TEMPLATE` 剪切
- [x] 6.2 扩展 `setup.py:deploy_skills` 支持 `.j2` 文件 Jinja2 渲染（检测 `.j2` 后缀 → 渲染 → 写入）
- [x] 6.3 删除 `setup.py:render_skill_md` 函数和 `SKILL_MD_TEMPLATE` 字符串
- [x] 6.4 更新 `setup.py:run_setup` 步骤列表，移除 `render_skill_md` 步骤（已由 deploy_skills 包含）

## 7. 前端跨页面状态

- [x] 7.1 在 `base.html` 新增 `Project` 对象（`current()`、`bind(path)`），删除 2 个 `htmx:configRequest` 监听器，替换为 1 个写 `X-Loop-Project` header 的监听器
- [x] 7.2 修改 `base.html:switchProject` 为先 `pushState` 再 `htmx.ajax`
- [x] 7.3 更新 `base.html` 中所有 Alpine 组件（`settingsForm`、`docsEditor`）的 `fetch()` 调用使用 `Project.bind()` 或 `Project.current()`
- [x] 7.4 删除 `settings.html` 中的 `?project={{ current_root }}` 硬编码
- [x] 7.5 删除 `control.html` 中手动 `URLSearchParams` 拼接
- [x] 7.6 确保 `resolve_project_root` 接受 `X-Loop-Project` header（任务 1.1 已处理，此处验证）

## 8. 心跳循环优化

- [x] 8.1 修改 `control.py:start_loop`，在 `subprocess.Popen` 后进入 Python 心跳 while 循环（`while proc.poll() is None: write_heartbeat(); sleep(30)`）
- [x] 8.2 精简 `loop.ps1` 生成逻辑，移除心跳 while 循环，仅保留终端窗口启动 + PID 写入 + SendKeys
- [x] 8.3 确认 `stop_loop` 和 Dashboard 控制页面行为不变

## 9. 收尾验证

- [x] 9.1 运行 `python -m pytest` 确认全部测试通过
- [x] 9.2 运行 `pip install -e ".[ui,test]"` 确认无依赖冲突
- [x] 9.3 运行 `loop --help` 确认 CLI 正常
- [x] 9.4 启动 `loop ui start`，浏览器验证 Dashboard 所有页面加载正常、项目切换不丢 project
- [x] 9.5 在某个 loop-engineering 管理的项目中运行 `loop setup --type python-server`，验证 setup 全流程正常
