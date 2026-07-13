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
<填写 Web 服务启动命令>
```
```bash
<填写就绪检查命令>
```
不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪些端点变了，是新增还是修改
2. 匹配合适的验证原语
3. 一次启动服务覆盖所有端点验证
4. 没有匹配的 → 跑**默认**流程

```bash
<填写默认验证命令>
```

## 可用工具

- `curl` — HTTP 请求
- `Python -c` — 内联脚本校验 JSON 结构
- <填写其他工具>

## 验证原语

### 端点响应校验

curl 目标端点 → 确认状态码和返回结构

```bash
<填写 curl 命令>
```

适用：新增或修改了 API 端点
扩展：若端点接受 query 参数 → 用不同参数值组合测试

### JSON 结构校验

```bash
<填写 JSON 校验命令>
```

适用：返回 JSON 的端点，需要确认返回字段不缺失

### 错误处理验证

故意触发错误 → 确认错误信息可读、状态码正确

```bash
<填写错误处理验证命令>
```

适用：新增或修改了错误处理逻辑

### <填写项目特有的验证原语>

<填写原语描述>

```bash
<填写验证命令>
```

适用：<填写适用条件>

## 探测

- 错误的 HTTP method → 应返回 405
- 不传必填参数 → 应返回 422，错误信息能看懂
- 不存在的资源 ID → 应返回 404
- 请求体 JSON 格式错误 → 应返回 422，不崩溃
- <填写项目特有的探测>

## 清理

同 `verifier-web`。
```bash
<填写清理命令>
```

## 自更新

- 新增端点 → 补充对应的验证方法
- API 框架换了 → 重新跑 `loop setup`
- <填写其他自更新规则>
