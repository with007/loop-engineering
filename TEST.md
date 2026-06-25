# 手动测试指南 — loop-engineering

> 项目类型: Python Server | 由 loop-test-init 定制
>
> 本文件是手动测试清单，在合入前按此检查。标有 🤖 的步骤
> verifier 已自动执行，你可以复核结果或重新执行。
> 重新运行 `loop setup` 会覆盖 — 有自定义内容请备份。

## 环境准备

```bash
pip install -e ".[ui]"
```

项目依赖：`pyyaml`、`jinja2`（核心）；`fastapi`、`uvicorn`、`python-multipart`（可选，仪表盘需要）。

> 🤖 verifier 执行时会自动 pip install。测试完成后记得
> 切回主 worktree 重新 `pip install -e ".[ui]"`。

## 启动项目

项目有两个入口：

**Web 仪表盘**（主要）:
```bash
loop ui start --port 8765
```
服务地址: http://127.0.0.1:8765

**CLI 工具**:
```bash
loop --help
loop config show
```

> 🤖 verifier 在验证时会后台启动服务、请求 API 端点、然后停止。

## 运行时验证

### Web 仪表盘

1. 浏览器打开 http://127.0.0.1:8765
2. 确认仪表盘首页正常加载（项目统计、通过率图表）
3. 导航到各页面：
   - `/tasks` — 任务列表正常显示
   - `/runs` — 运行历史正常显示
   - `/control` — 循环控制界面正常显示
   - `/settings` — 配置编辑页面正常显示
4. 用 curl 检查关键 API：
   ```bash
   curl http://127.0.0.1:8765/api/projects/overview
   curl http://127.0.0.1:8765/api/tasks/list
   ```

### CLI 工具

1. `loop --help` — 确认所有子命令正常显示
2. `loop config show` — 确认能读取并显示项目配置
3. `loop setup --help` — 确认参数列表完整

## 测试完成后

1. 停止服务（Ctrl+C）
2. 检查终端无异常日志
3. **切回主 worktree 重新安装依赖**：
   ```bash
   pip install -e ".[ui]"
   ```

## 测试清单

### 1. 仪表盘页面加载

**步骤**:
1. 运行 `loop ui start --port 8765`
2. 浏览器打开 http://127.0.0.1:8765
3. 确认所有页面（仪表盘、任务、运行记录、控制、设置）正常加载
4. 停止服务

**预期**: 所有页面正常加载，无白屏或 500 错误

### 2. CLI 基础功能

**步骤**:
1. 运行 `loop --help`
2. 运行 `loop config show`
3. 确认输出格式正确、无乱码

**预期**: CLI 命令正常执行，输出格式正确

### 3. API 端点响应

**步骤**:
1. 启动 `loop ui start --port 8765 --no-browser`
2. curl `http://127.0.0.1:8765/api/projects/overview` — 确认返回 JSON 含项目名
3. curl `http://127.0.0.1:8765/api/tasks/list` — 确认返回任务列表
4. 停止服务

**预期**: API 返回 200，JSON 结构正确
