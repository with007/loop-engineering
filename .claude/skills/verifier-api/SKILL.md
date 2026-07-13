---
name: verifier-api
description: >
  API endpoint verification. Tests endpoints via curl, checks status codes,
  response structure, and error handling.
---

# verifier-api

验证 API 端点变更。

## 启动检查

同 `verifier-web`——复用同一个服务。若服务已在运行则跳过：
```bash
loop ui start --port 8765 --no-browser &
```
```bash
PORT=8765; for i in $(seq 0 4); do
  P=$((PORT + i))
  curl -sf http://127.0.0.1:$P/ > /dev/null 2>&1 && echo "READY:$P" && break
  sleep 2
  curl -sf http://127.0.0.1:$P/ > /dev/null 2>&1 && echo "READY:$P" && break
done
```
不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪些端点变了，是新增还是修改
2. 匹配合适的验证原语
3. 一次启动服务覆盖所有端点验证
4. 没有匹配的 → 跑**默认**流程

```bash
# 默认：逐个调所有 API 模块的代表性端点，确认返回 200
for ep in /api/projects/list /api/tasks/list /api/runs/list /api/control/status /api/branches/list /api/config/show /api/sync/status; do
  echo -n "$ep: "
  curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT$ep"
  echo
done
```

## 可用工具

- `curl` — HTTP 请求
- `Python -c` — 内联脚本校验 JSON 结构

## 验证原语

### 端点响应校验

curl 目标端点 → 确认状态码和返回结构

```bash
curl -sf "http://127.0.0.1:$PORT/api/<endpoint>" | python -m json.tool | head -20
```

适用：新增或修改了 API 端点
扩展：若端点接受 query 参数 → 用不同参数值组合测试

### JSON 结构校验

```bash
curl -sf "http://127.0.0.1:$PORT/api/<endpoint>" | python -c "
import json, sys
data = json.load(sys.stdin)
# 确认关键字段存在
assert '<关键字段>' in str(data), 'Missing key field'
print('OK: structure valid')
"
```

适用：返回 JSON 的端点，需要确认返回字段不缺失

### 错误处理验证

故意触发错误 → 确认错误信息可读、状态码正确

```bash
# 错误 HTTP method
curl -sf -o /dev/null -w "%{http_code}" -X PATCH "http://127.0.0.1:$PORT/api/control/start"
echo " (expected 405)"
# 不存在的资源
curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/projects/nonexistent"
echo " (expected 404)"
```

适用：新增或修改了错误处理逻辑

### 控制操作链验证

本项目 `/api/control/` 端点构成状态机：start → pause → resume → stop。验证完整操作链的状态转换。

```bash
# 完整控制链
curl -sf -X POST "http://127.0.0.1:$PORT/api/control/start" -d '{}' && echo " start OK"
sleep 1
curl -sf "http://127.0.0.1:$PORT/api/control/status" | python -c "import json,sys; d=json.load(sys.stdin); assert d.get('running'), 'not running'; print('status after start: running')"
curl -sf -X POST "http://127.0.0.1:$PORT/api/control/pause" -d '{}' && echo " pause OK"
curl -sf "http://127.0.0.1:$PORT/api/control/status" | python -c "import json,sys; d=json.load(sys.stdin); assert d.get('paused'), 'not paused'; print('status after pause: paused')"
curl -sf -X DELETE "http://127.0.0.1:$PORT/api/control/pause" && echo " resume OK"
curl -sf "http://127.0.0.1:$PORT/api/control/status" | python -c "import json,sys; d=json.load(sys.stdin); assert d.get('running') and not d.get('paused'), 'not resumed'; print('status after resume: running')"
curl -sf -X POST "http://127.0.0.1:$PORT/api/control/stop" -d '{}' && echo " stop OK"
curl -sf "http://127.0.0.1:$PORT/api/control/status" | python -c "import json,sys; d=json.load(sys.stdin); assert not d.get('running'), 'still running'; print('status after stop: stopped')"
```

适用：control API 变更、状态机逻辑变更
注意：此原语会实际触发控制操作（启动/停止 loop 进程），在非隔离环境中慎用

## 探测

- 错误的 HTTP method → 应返回 405
  ```bash
  curl -sf -o /dev/null -w "%{http_code}" -X PATCH "http://127.0.0.1:$PORT/api/control/status"
  ```
- 不传必填参数 → 应返回 422，错误信息能看懂
  ```bash
  curl -sf -w "\n%{http_code}" -X POST "http://127.0.0.1:$PORT/api/tasks/add" -d "description="
  ```
- 不存在的资源 ID → 应返回 404
  ```bash
  curl -sf -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/projects/00000000"
  ```
- 请求体 JSON 格式错误 → 应返回 422，不崩溃
  ```bash
  curl -sf -w "\n%{http_code}" -X POST "http://127.0.0.1:$PORT/api/control/start" -H "Content-Type: application/json" -d "{invalid"
  ```
- `POST /api/control/start` 重复调用（loop 已在运行）→ 应返回合理状态码，不崩溃不重复启动
  ```bash
  curl -sf -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/control/start" -d '{}'
  ```
- `POST /api/tasks/add` 不传 assignee → 应返回 422

## 清理

同 `verifier-web`。
```bash
FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr ":$PORT"') DO taskkill /f /pid %P 2>nul
```

## 自更新

- 新增端点 → 补充对应的验证方法
- API 框架换了 → 重新跑 `loop setup`
- control API 状态机逻辑变了 → 更新控制操作链原语
- 端点路径或参数变了 → 更新对应 curl 命令和探测项
