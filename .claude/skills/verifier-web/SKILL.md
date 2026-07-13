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
<填写 Web 服务启动命令>
```
```bash
<填写就绪检查命令>
```
不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪些模板/页面变了，变了什么
2. 匹配下方验证原语的适用条件，选择匹配的
3. 设计针对性方案：不跑无关步骤，一次启动服务覆盖所有
4. 没有匹配的 → 跑**默认**流程

```bash
<填写默认验证命令>
```

## 可用工具

- `curl` — HTTP 请求
- `WebFetch` — 加载页面确认元素
- Playwright — 浏览器交互
- Jinja2 渲染 — 模板渲染验证
- <填写其他工具>

## 验证原语

### 模板验证

用 Jinja2 渲染变更的 `.j2` 模板 → assert 关键字段存在。
用 curl 调对应的 fragment 端点（带 `HX-Request: true`）→ 确认 HTML 正确渲染、无报错。

```bash
<填写 Jinja2 渲染验证命令>
```
```bash
<填写 fragment 端点 curl 命令>
```

适用：`.html` / `.j2` 模板变更
扩展：若引用了新的 Alpine.js 指令或 JS 函数 → 确认代码库中有对应实现

### 页面验证

WebFetch 目标页面 → 确认关键元素存在（导航栏、主内容区、无空白页）。
若涉及交互逻辑 → Playwright 模拟真实操作路径。

```bash
<填写 WebFetch 或 Playwright 命令>
```

适用：页面结构变更、路由变更、JS/HTMX 行为变更
注意：只加载 diff 涉及的页面

### <填写项目特有的验证原语>

<填写原语描述>

```bash
<填写验证命令>
```

适用：<填写适用条件>

## 探测

- 请求不存在的页面 → 应返回 404，不崩溃
- 快速连续多次请求 → 不报错
- 并发请求 → 不冲突
- <填写项目特有的探测>

## 清理

```bash
<填写清理命令>
```
确认端口无残留进程。

## 自更新

- 启动命令或端口变了 → 更新上方命令
- 项目新增页面 → 补充到页面列表
- 框架换了（如 FastAPI → Flask）→ 重新跑 `loop setup`
- <填写其他自更新规则>
