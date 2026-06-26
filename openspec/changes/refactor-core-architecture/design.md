## Context

Loop Engineering 是一个 Python CLI + FastAPI Dashboard 项目，管理 Claude Code agent 的自主任务执行循环。当前代码库的单体特征逐渐成为维护负担：

- `server/app.py`（757 行）承载了路由、业务逻辑、HTML 片段生成
- `setup.py`（1355 行）包含 560 行的内联 Jinja2 模板字符串
- `_project_root` 等工具函数在 10+ 个文件中各自实现
- `tasks.md` 格式被 4 个不同的正则解析器消费
- 前端跨页面状态（`?project=`）通过两个 `htmx:configRequest` 监听器维护，频繁丢失
- 没有任何测试

本次重构在保持所有 API 和外部行为不变的前提下，改善代码结构。

## Goals / Non-Goals

**Goals:**
- 消除重复代码（工具函数、tasks.md 解析器、状态过滤逻辑）
- 提高可测试性（纯函数模块优先覆盖）
- 前端状态管理收敛到单一入口
- 模板文件与 Python 源码分离
- 配置文件写入原子化

**Non-Goals:**
- 不引入新的 Web 框架或前端框架
- 不改变 API 端点签名（仅新增可选的 HTTP header）
- 不改动预设系统（`presets.py` 保持现状）
- 不改动 tasks.md 的存储格式（仍为 markdown）
- 不重写 PowerShell 终端窗口启动逻辑（SendKeys 保留）

## Decisions

### 1. server/ 拆分策略：先 services 后 routers

**决定**：分两步进行。第一步从 `app.py` 提取纯逻辑到 `services/`（无路由依赖），第二步拆分路由到 `routers/`。

**理由**：`services/` 层不依赖 FastAPI，可以先提取、先测试，风险最低。`routers/` 拆分是纯搬家，URL 路径不变，Jinja2 模板不变。

**替代方案**：一步到位拆成多个蓝图。拒绝原因——步子太大，验证困难。

**目标结构**：
```
server/
├── app.py                  ← FastAPI() 实例 + router 注册 + start_server()
├── dependencies.py         ← _project_root(), _agent_name() 等共享依赖
├── routers/
│   ├── pages.py            ← /, /tasks, /runs, /control, /settings, /setup
│   └── fragments.py        ← /control/status-fragment, /tasks/list-items 等 HTMX 片段
├── services/
│   ├── task_parser.py      ← parse_tasks(), filter_tasks() — 统一解析+过滤
│   └── project_context.py  ← build_projects_context() — 项目列表上下文
├── api/                    ← 现有 API routers 保持不动
│   └── ...
└── templates/              ← 不变
```

### 2. 模板分离：SKILL_MD_TEMPLATE → templates/skills/task-runner/SKILL.md.j2

**决定**：将 `setup.py` 中的 560 行内联字符串移到 `templates/skills/task-runner/SKILL.md.j2`。`deploy_skills()` 扩展为支持 `.j2` 文件渲染（检测 `.j2` 后缀 → Jinja2 渲染 → 写入）。删除 `render_skill_md()` 函数。

**理由**：项目已有 `templates/verify/{type}/*.j2` 和 `templates/skills/{name}/SKILL.md` 两种模板模式。`SKILL.md.j2` 将两者统一——位于 `templates/skills/` 下，用 Jinja2 渲染。语法高亮、版本 diff、编辑体验均受益。

### 3. 工具函数合并：path_utils.py

**决定**：新增 `src/loop_engineering/path_utils.py`，提供 4 个函数：

| 函数 | 替代 | 说明 |
|------|------|------|
| `find_project_root(start_dir?)` | `_find_project_root()` × 4 | 向上搜索 loop-config.yaml |
| `resolve_project_root(project?, request?)` | `_project_root()` × 10 | 多来源解析（header > param > env > cwd） |
| `get_default_branch(repo_path?)` | `_default_branch()` × 3 | 优先级: local master > main > origin/master > origin/main |
| `get_agent_dir(config)` | `os.path.join(...)` × 11 | agent worktree 路径推导 |

**理由**：这些函数在各自文件里是 private 函数，但实际是公共基础设施。统一后加 System32 guard 这类通用防护只需改一处。

**resolve_project_root 的解析优先级**：
1. `X-Loop-Project` HTTP header（前端 HTMX 自动带）
2. `?project=` query param（curl 用户、初始页面加载）
3. `LOOP_PROJECT_ROOT` env var（服务启动时设置）
4. `os.getcwd()` 向上搜索（兜底）

### 4. 前端状态：Project 对象 + HTTP Header

**决定**：`base.html` 中用一个 `Project` 对象替代所有分散的 `window.location.search` 读取。`htmx:configRequest` 监听器合并为一个，统一追加 `X-Loop-Project` header（不再追加 query param）。

**理由**：当前有 2 个 `htmx:configRequest` 监听器、9 处 `URLSearchParams(window.location.search).get('project')`、以及多个模板中的 `?project={{ current_root }}` 硬编码。Header 方案的优势是不受 URL 拼接逻辑影响、不和已有 query param 冲突。

**改动范围**：
- `base.html`：新增 `Project` 对象 + 单一 `htmx:configRequest` 监听器（写 header）
- `base.html`：`switchProject` 改为先 `pushState` 再 `htmx.ajax`
- `settings.html`：删除 `?project={{ current_root }}` 硬编码
- `control.html`：删除手动 `URLSearchParams` 拼接
- 其他模板：删除所有 `?project=` 手动拼接（由 header 自动携带）

### 5. tasks.md 解析统一：TaskLine 类

**决定**：在 `task_id.py` 中新增 `TaskLine` dataclass，提供 `parse(line) -> TaskLine | None` 和 `format() -> str`。所有 tasks.md 读写操作改用 `TaskLine`。

**理由**：4 个不同的正则解析器（`app.py:_read_tasks`、`api/tasks.py:list_tasks`、`task_pick.py`、`task_done.py`）消费同一格式。`TaskLine` 提供单一真相来源，且 `parse(format(x)) == x` 自反性可通过测试保证。

**顺带修复**：`/api/tasks/add` 端点当前不生成 `[task_id]`，改用 `TaskLine` 后自动补上。

### 6. 脚本协议：--format=shell

**决定**：`task_pick`/`task_done`/`task_cleanup` 新增 `--format` 参数。`--format=shell` 输出 `shlex.quote` 转义的 shell 变量赋值，调用方用 `eval $(...)` 消费。默认保持当前格式（向后兼容）。

**输出示例**：
```bash
# --format=shell
STATUS=ok
TASK_ID=a1b2c3d4
BRANCH=agent/with/a1b2c3d4-fix-login
```

**理由**：`eval` 是 bash 原生机制，LLM 在 SKILL.md 中无需手写正则解析器。`shlex.quote` 保证了空格和特殊字符安全。比 JSON 方案对 bash 调用方更友好（无需依赖 `jq`）。

### 7. 原子写入：atomic_write()

**决定**：新增 `utils.py`，提供 `atomic_write(path, content)` 函数（`tempfile.mkstemp` + `os.replace`）。仅用于配置文件（`loop-config.yaml`、`.mcp.json`、`McpProjectConfig.json`、run log JSON）。心跳、暂停、PID 等微文件不改。

**理由**：配置文件损坏的影响远大于心跳文件——配置丢失需要重新 setup，心跳丢失只是几分钟内认为 loop 不在运行。微文件有 try/except 兜底且写入频繁，atomic write 的 overhead 不值得。

### 8. 心跳循环：PS → Python

**决定**：`start_loop()` 中，PowerShell 脚本只负责启动终端窗口和 SendKeys，心跳 while 循环移到 Python 端管理（`subprocess.Popen` 后进入 `while proc.poll() is None: write_heartbeat(); sleep(30)`）。

**理由**：Python 端的异常处理和可读性优于 PowerShell。Python 能访问 `control.py` 的 `write_heartbeat()` 函数，不再通过 `[System.IO.File]::WriteAllText` 写文件。SendKeys 逻辑保留在 PS 中（无法绕过），但 PS 脚本从 ~25 行缩到 ~8 行。

### 9. 测试策略：从纯函数开始

**决定**：首组测试覆盖 `task_id.py`（纯函数，零依赖），后续可扩展 `test_config.py`（deep_merge）、`test_control.py`（文件 IPC 状态机）、`test_runlog.py`（写入/查询/过滤）。

**测试结构**：
```
tests/
├── test_task_id.py       ← 首组：generate, parse, slug, branch_name
├── test_config.py        ← 后续：deep_merge, detect_config
├── test_control.py       ← 后续：heartbeat, pause, throttle 状态机
└── conftest.py           ← tmp_path fixtures
```

## Risks / Trade-offs

- **app.py 拆分后路由分散**：新增路由需要在 `routers/pages.py` 和 `routers/fragments.py` 之间选择 → 按"返回完整页面还是 HTMX 片段"判断，有明确的分界标准
- **Header 方案依赖 HTMX 监听器**：非 HTMX 请求（如 `fetch()` API 调用）不会自动带 header → Alpine 组件中的 `fetch()` 需手动读取 `Project.current()` 加 header。改动范围已知（`base.html` 中 5 处 Alpine `loadConfig` 等函数）
- **原子写入跨平台**：`os.replace` 在 Windows/Linux 上均为原子语义 → 无风险
- **`--format=shell` 增加脚本参数复杂度**：默认格式不变，SKILL.md 模板更新后统一用 `--format=shell` → 过渡期兼容

## Open Questions

- `claude -p '/runloop'` 能否保持会话存活？→ 验证后才能判断能否去掉 SendKeys（本次不依赖此结论，心跳搬回 Python 已经是独立改进）
