# 验证指南 — loop-engineering

> 项目类型: Python Server | 由 loop-test-init 定制
>
> 本文件是**验证方法论参考**，不是必须全部执行的清单。
> verifier 子代理按此执行。
> 验证范围由变更驱动 — 只执行涉及模块的步骤，未涉及的跳过。
> 重新运行 `loop setup` 会覆盖 — 有自定义内容请备份。
>
> 通用验证（diff 审查、变更范围确认等）由 task-runner 框架统一处理。

## 测试工具

| 工具 | 用途 |
|------|------|
| curl | HTTP 请求，检查 API 状态码和返回结构 |
| WebFetch | 加载页面，确认关键元素存在 |
| Python -c | 内联脚本，assert 检查返回值 |
| Jinja2 渲染 | 用真实数据渲染模板，验证输出内容 |
| pytest | 测试框架，执行项目测试用例 |
| Bash 命令 | CLI 验证（--help）、进程管理（启动/停止服务） |

## 自动化验证手段

以下是 verifier 可用的自动化验证方法。

### 1. 运行测试

```bash
python -m pytest || echo "SKIPPED: no test framework configured"
```

项目目前无测试框架，自动跳过。如果后续添加了 pytest 配置，verifier 会自动执行。

### 2. 代码逻辑检查

读变更文件的 diff，检查：
- 条件分支覆盖边界情况
- 函数入参/出参与调用方匹配
- 异常路径有处理
- 导入的模块存在且版本兼容

关键模块及检查重点：
- `setup.py`：worktree 创建、MCP 配置部署、模板渲染逻辑
- `server/app.py` / `server/api/*.py`：FastAPI 路由、请求处理、错误恢复
- `cli.py`：CLI 参数解析、子命令分发
- `presets.py`：预设类型配置和模板变量生成
- `control.py`：IPC 文件信号（heartbeat、pause、throttle）
- `config.py`：YAML 配置读写和项目检测

### 3. 模板检查

变更涉及 `.html` / `.j2` 文件时执行：

```bash
# 用真实数据渲染模板，检查关键字段
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates/verify/python-server'))
tmpl = env.get_template('VERIFY.md.j2')
result = tmpl.render(project_name='test', preset_display_name='Python Server')
assert '验证指南' in result, 'VERIFY.md: missing title'
assert '运行测试' in result, 'VERIFY.md: missing section'
print('VERIFY.md.j2: OK')
"
```

HTML 模板变更时额外检查：
- 模板引用的 JS 函数（HTMX、Alpine.js、Chart.js、marked.js）在 `base.html` 的 `<script>` 中加载
- `x-model` / `@click` 等 Alpine 指令对应的 store/函数在 JS 代码中存在

### 4. 运行时验证

#### 4a. 安装依赖

```bash
pip install -e ".[ui]"
```
exit code 0 = 通过。

#### 4b. CLI 验证

```bash
loop --help              # 确认子命令列表完整，exit code 0
loop config show         # 确认能读取配置，exit code 0
```

#### 4c. Web 服务

```bash
# 后台启动服务
loop ui start --port 8765 --no-browser &
SERVER_PID=$!
sleep 3
```

API 端点（curl 检查）：
```bash
# 概览 API
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/api/projects/list
# 期望: 200

# 任务列表 API
curl -s http://127.0.0.1:8765/api/tasks/list | python -c "import sys,json; d=json.load(sys.stdin); assert 'tasks' in d or isinstance(d, list), 'missing tasks'"
# 期望: JSON 结构正确
```

Web 页面（WebFetch 检查关键元素）：
- `http://127.0.0.1:8765/` — 确认含"通过率"或"项目"
- `http://127.0.0.1:8765/tasks` — 确认含"任务"
- `http://127.0.0.1:8765/settings` — 确认含"VERIFY.md"或"TEST.md"

停止服务：
```bash
kill $SERVER_PID 2>/dev/null
```

## 模块验证示例

以下是各模块的自动化验证示例。verifier **只运行变更涉及模块**的步骤。

### 仪表盘页面

**触发条件**: 变更涉及 `server/templates/` 下的 HTML 文件。

**验证步骤**:
1. 读 diff，确认 HTML 中新增的 Alpine.js 指令/jinja2 变量有对应实现
2. `pip install -e ".[ui]"` 后启动服务
3. curl `/api/projects/list` 确认 200
4. WebFetch `/` ~ `/tasks` ~ `/settings` 三个页面，确认关键元素存在
5. 停止服务

### CLI 命令

**触发条件**: 变更涉及 `cli.py` 或 `config.py`。

**验证步骤**:
1. `pip install -e ".[ui]"`
2. `loop --help` — exit code 0
3. `loop config show` — exit code 0，输出含 project.name
4. 如果新增子命令：`loop <新命令> --help` — exit code 0

### API 端点

**触发条件**: 变更涉及 `server/api/` 或 `server/app.py`。

**验证步骤**:
1. `pip install -e ".[ui]"` 后启动服务
2. curl 变更涉及的端点，检查状态码和 JSON 结构
3. 确认新增端点有对应的前端页面调用
4. 停止服务

### 模板渲染

**触发条件**: 变更涉及 `templates/` 下的 `.j2` 文件。

**验证步骤**:
1. 用 jinja2 Environment + FileSystemLoader 渲染变更的模板
2. Python assert 检查渲染结果包含关键字段
3. 确认模板变量在 `presets.py` 的 `PRESETS` 中有对应类型定义

> 如果变更涉及以上未列出的新模块，参照"自动化验证手段"推导合适的验证步骤。
> 验证通过后建议将新模块的验证示例添加到本文档。
