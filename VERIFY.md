# 验证指南 — loop-engineering

> 项目类型: Python Server | 由 loop-test-init 定制
>
> 本文件定义项目特定的自动验证步骤。verifier 子代理按此顺序执行。
> 重新运行 `loop setup` 会覆盖 — 有自定义内容请备份。
>
> 通用验证（diff 审查、变更范围确认等）由 task-runner 框架统一处理。

## 自动化验证流水线

### 1. 运行测试

项目目前没有配置测试框架（无 test_*.py 文件、pytest 配置或 CI 流水线）。
verifier 会自动跳过。

- **命令**: 跳过（项目暂无测试）
- **通过条件**: N/A

### 2. 代码逻辑检查

检查本次变更涉及的核心逻辑是否正确：
- `setup.py`：worktree 创建、MCP 配置部署、技能模板渲染逻辑
- `server/app.py` 和 `server/api/*.py`：FastAPI 路由、请求处理、错误恢复
- `cli.py`：CLI 参数解析、子命令分发
- `presets.py`：预设类型配置和模板变量生成
- `control.py`：IPC 文件信号（heartbeat、pause、throttle）
- `config.py`：YAML 配置读写和项目检测

### 3. 模板检查

项目大量使用 Jinja2 模板，必须检查：
- `src/loop_engineering/server/templates/` — 仪表盘 HTML 模板
- `templates/verify/*/` — VERIFY.md / TEST.md 的 Jinja2 模板
- `templates/skills/*/SKILL.md` — 技能定义模板

变更涉及模板时:
- 用真实配置数据渲染模板，检查生成的 markdown/HTML 内容
- 确认模板中引用的 JS 函数（HTMX、Alpine.js、Chart.js、marked.js）在 base.html 中正确加载

### 4. 运行时验证

项目有 CLI 和 Web 两个入口点，分别验证。

**CLI 工具**:
```bash
loop --help              # 确认子命令列表完整
loop config show         # 确认能读取配置
```

**Web 服务**:
```bash
loop ui start --port 8765 --no-browser
```
- 用 curl 请求 `http://127.0.0.1:8765/api/projects/overview` 检查 API 响应
- 用 WebFetch 加载 `http://127.0.0.1:8765/` 确认仪表盘页面包含关键元素
- 停止服务

- **命令**: loop ui start --no-browser
- **通过条件**: 服务启动后 API 返回 200，页面正常加载
