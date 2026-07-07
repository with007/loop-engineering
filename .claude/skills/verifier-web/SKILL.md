---
name: verifier-web
description: >
  Web page and fragment verification. Launches the server, checks fragment
  endpoints via curl, loads pages via WebFetch, tests browser interaction.
---

# verifier-web

验证 Web 页面和 HTML 模板变更。

## 启动检查

```bash
loop ui start --port 8765 --no-browser &
```
```bash
# 等待启动，端口被占则自动 +1 重试（最多 5 次）
PORT=8765; for i in $(seq 0 4); do
  P=$((PORT + i))
  curl -sf http://127.0.0.1:$P/ > /dev/null 2>&1 && echo "READY:$P" && break
  sleep 2
  curl -sf http://127.0.0.1:$P/ > /dev/null 2>&1 && echo "READY:$P" && break
done
```
不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪些模板/页面变了，变了什么
2. 匹配下方验证原语的适用条件，选择匹配的
3. 设计针对性方案：不跑无关步骤，一次启动服务覆盖所有
4. 没有匹配的 → 跑**默认**流程

```bash
# 默认：curl 首页 + WebFetch dashboard 确认元素
curl -sf http://127.0.0.1:$PORT/ | head -20
curl -sf http://127.0.0.1:$PORT/tasks | head -20
```

## 可用工具

- `curl` — HTTP 请求
- `WebFetch` — 加载页面确认元素
- Playwright — 浏览器交互
- Jinja2 渲染 — 模板渲染验证

## 验证原语

### 模板验证

用 Jinja2 渲染变更的 `.html` 模板 → assert 关键字段存在。
用 curl 调对应的 fragment 端点（带 `HX-Request: true`）→ 确认 HTML 正确渲染、无报错。

```bash
# Jinja2 渲染验证（在 Python 环境内执行）
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('src/loop_engineering/server/templates'))
tmpl = env.get_template('<变更的模板名>.html')
rendered = tmpl.render(request={})
assert '<关键字段>' in rendered, 'Missing key element'
print('OK')
"
```
```bash
# Fragment 端点验证
curl -sf -H "HX-Request: true" "http://127.0.0.1:$PORT/tasks/list" | head -30
```

适用：`.html` / `.j2` 模板变更
扩展：若引用了新的 Alpine.js 指令或 JS 函数 → 确认代码库中有对应实现

### 页面验证

WebFetch 目标页面 → 确认关键元素存在（导航栏、主内容区、无空白页）。
若涉及交互逻辑 → Playwright 模拟真实操作路径。

```bash
# WebFetch 关键页面
WebFetch http://127.0.0.1:$PORT/ "确认 dashboard 页面包含项目列表、导航栏，无空白页"
WebFetch http://127.0.0.1:$PORT/tasks "确认任务页面包含任务列表、筛选控件"
```

适用：页面结构变更、路由变更、JS/HTMX 行为变更
注意：只加载 diff 涉及的页面

### HTMX Fragment 轮询验证

本项目大量使用 HTMX 5s 轮询。验证轮询链路完整：status-fragment → info-fragment → list-items。

```bash
# 模拟一轮完整轮询
curl -sf "http://127.0.0.1:$PORT/control/status-fragment" | head -5
curl -sf "http://127.0.0.1:$PORT/control/info-fragment" | head -5
curl -sf "http://127.0.0.1:$PORT/tasks/list-items" | head -5
# 确认每个返回非空 HTML，不含 500 错误
```

适用：fragment 端点变更、轮询逻辑变更、控制面板状态机变更
扩展：若轮询间隔变了 → 确认新间隔生效

## 探测

- 请求不存在的页面 → 应返回 404，不崩溃
  ```bash
  curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/nonexistent"
  ```
- 快速连续多次请求 → 不报错
  ```bash
  for i in $(seq 1 10); do curl -sf -o /dev/null -w "%{http_code} " "http://127.0.0.1:$PORT/"; done
  ```
- 并发请求 → 不冲突
  ```bash
  curl -sf "http://127.0.0.1:$PORT/" & curl -sf "http://127.0.0.1:$PORT/tasks" & curl -sf "http://127.0.0.1:$PORT/runs" & wait
  ```
- 不带 `project` 参数请求 `/tasks` `/runs` `/control` → 应 fallback 到已注册项目或重定向到 setup，不 500
  ```bash
  curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/tasks"
  ```
- 带 `HX-Request: true` 请求完整页面 → 确认返回的是完整页面（非 fragment），行为正确

## 清理

```bash
# Windows
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*" 2>nul
# 或按端口杀
FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr ":$PORT"') DO taskkill /f /pid %P 2>nul
```
确认端口无残留进程。

## 自更新

- 启动命令或端口变了 → 更新上方命令
- 项目新增页面或 fragment 端点 → 补充到页面列表和原语
- 框架换了（如 FastAPI → Flask）→ 重新跑 `loop setup`
- 轮询间隔或 fragment 端点路径变了 → 更新 HTMX Fragment 轮询原语
- 页面路由规则变了（如新增 query 参数）→ 更新探测项
