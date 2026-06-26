## Why

Loop Engineering 项目经过多轮迭代后，代码库积累了多个结构性债务：路由层混杂业务逻辑、公共函数重复散布各处、隐式契约（tasks.md 格式、跨页面状态）分散在多个各自实现的解析器中、前端状态丢失 bug 频繁出现。这些问题不阻碍功能，但每次修改都需要触碰多处代码，且没有测试保护。在 bug 频率上升之前做一次集中整理。

## What Changes

### 实现层改进

- **拆分 `app.py`**：提取 `services/task_parser.py`（统一 tasks.md 解析）、`services/project_context.py`（项目上下文构建），拆分 `routers/pages.py` 和 `routers/fragments.py`
- **SKILL_MD_TEMPLATE 独立化**：从 `setup.py` 560 行内联字符串 → `templates/skills/task-runner/SKILL.md.j2`，与其他 skill 模板一致
- **合并重复工具函数**：`_project_root`（10 处）、`_default_branch`（3 处）、`_find_project_root`（4 处）→ `path_utils.py`
- **脚本 stdout 协议结构化**：`task_pick` 等脚本加 `--format=shell`，调用方用 `eval $(...)` 消费，替代脆弱的手工正则解析
- **原子写入**：config/JSON/YAML 写入改用 `atomic_write()`（tempfile + rename），心跳/暂停等微文件不改
- **添加 pytest 测试**：从 `test_task_id.py` 起步，`pyproject.toml` 加 `test` 可选依赖

### 设计层改进

- **跨页面状态收敛**：`base.html` 中的 `Project` 对象 + `X-Loop-Project` HTTP Header，替代分散的 `window.location.search` 读取
- **TaskLine 统一解析**：`task_id.py` 新增 `TaskLine` 类，统一 tasks.md 的解析和格式化（消除 4 个不同正则）
- **`get_agent_dir()` 集中计算**：`config.py` 新增函数，替代 11 处 `os.path.join(agent_workspace, project_name)`
- **心跳循环从 PS 搬回 Python**：`start_loop()` 的心跳写入由 Python 管理，PowerShell 脚本仅保留终端窗口启动 + SendKeys

## Capabilities

### New Capabilities

- `server-structure`: app.py 模块化拆分（services/routers）、SKILL_MD_TEMPLATE 独立文件
- `path-utils`: 统一的 `find_project_root`、`resolve_project_root`、`get_default_branch`、`get_agent_dir` 工具函数
- `task-parser`: `TaskLine` 类统一 tasks.md 的解析、格式化、状态转换
- `script-protocol`: `--format=shell` 输出模式，`eval` 安全消费
- `atomic-writes`: 配置文件的原子写入工具函数
- `cross-page-state`: 前端 `Project` 状态对象 + `X-Loop-Project` header 机制
- `loop-startup`: 心跳循环从 PowerShell 移至 Python 管理
- `test-infra`: pytest 测试基础设施和 `test_task_id.py` 首组测试

### Modified Capabilities

无（所有改动是实现层面的重构，不改变已有 spec 的行为约定）

## Impact

- **代码文件**：`server/app.py`（拆分）、`setup.py`（模板外提 + 心跳简化）、`config.py`（新增函数）、`task_id.py`（新增 TaskLine）、`control.py`（心跳逻辑）、新增 `path_utils.py`、`services/`、`routers/`
- **模板文件**：`templates/skills/task-runner/SKILL.md.j2`（新增）、`base.html`（JS 重构）、`settings.html`、`control.html`、`_tasks_items.html`（删手动 project= 拼接）
- **依赖**：`pyproject.toml` 新增 `test` optional-dependencies（pytest）
- **API**：无新增/移除端点；所有 API 端点新增接受 `X-Loop-Project` header（向后兼容，query param 继续可用）
- **CLI**：`task_pick`/`task_done`/`task_cleanup` 新增 `--format` 参数（默认行为不变）
- **Breaking**：无
