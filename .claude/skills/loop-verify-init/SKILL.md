---
name: loop-verify-init
description: >
  交互式初始化项目的 verifier skills。扫描项目结构，识别表面，与用户确认后
  生成或定制 .claude/skills/verifier-*/SKILL.md。每个表面逐一处理，用户
  可确认、修改或跳过。
user_invocable: true
---

# loop-verify-init

你和用户一起，为项目创建一套完善的 verifier skills。不要全部自动搞定然后汇报结果——而是每一步让用户参与决策。

## Verifier skill 规范

无论定制还是冷启动生成，每个 verifier skill 必须包含以下 7 章。每章至少一个 `<填写...>` 占位符，通用内容保留，项目特有的用占位符。

| 章节 | 内容 |
|------|------|
| **启动检查** | 怎么确认表面可达。不通 → BLOCKED |
| **使用方法** | 教 loop-verify 怎么读：读 diff → 匹配原语 → 设计方案 → 合并 → 默认兜底 |
| **可用工具** | 该表面的工具列表。无特殊工具则写"不需要特殊工具" |
| **验证原语** | 每个原语：描述 + 命令 + 适用条件。必须包含一个项目特有原语占位符 |
| **探测** | 通用探测项 + 至少一条项目特有探测占位符 |
| **清理** | 停服务 / 关进程 / 或说明不需要清理 |
| **自更新** | 什么情况下更新这个 skill。必须包含项目特有自更新规则占位符 |

不放在 skill 里：项目简介 → CLAUDE.md。验证方法论 / 报告格式 / 变更范围 → loop-verify。

## 流程

### 1. 了解项目

先花时间理解项目，不要上来就问：

- 读 `loop-config.yaml` — 项目类型、端口、agent 名
- 读 `setup.py` / `pyproject.toml` — CLI 入口点、依赖
- 读 `.mcp.json` — MCP 配置（如果有）
- 浏览项目目录结构 — 有哪些模块、页面、端点

### 2. 识别表面

扫描项目，列出你发现的表面。对于每个表面，给出你的**判断依据**。

用 `AskUserQuestion` 让用户确认：

```
我发现以下表面：

1. Web 页面 — 检测到 server/templates/*.html
2. API — 检测到 server/api/
3. CLI — 检测到 cli.py + setup.py console_scripts
4. Desktop GUI — 未检测到 desktop/ 目录

是否有遗漏或不准确的？
```

用户确认后进入下一步。

### 3. 逐表面处理

对每个确认的表面，做三件事：确认启动方式 → 确认验证内容 → 生成/更新 skill。

#### 3a. 确认启动方式

先展示你推导出的启动命令，让用户确认或修正：

```
## verifier-web

我推导的启动命令：
  loop ui start --port 8765 --no-browser

就绪检查：
  curl -sf http://127.0.0.1:8765/api/projects/list

是否正确？端口需要改吗？有额外的环境变量或前置步骤吗？
```

#### 3b. 确认验证内容

展示你打算写进 skill 的验证步骤和探测项，让用户增删：

```
验证步骤（我打算写的）：
- curl fragment 端点确认模板正确渲染
- WebFetch 关键页面确认元素存在
- Playwright 点击按钮验证交互

探测项：
- 不传 project 参数
- 带 HX-Request header
- 不存在的页面

有需要补充的吗？比如项目特有的页面、已知的坑？
```

#### 3c. 生成或更新 skill

- **skill 已存在**（setup 复制过来的）→ 填占位符 + 按用户反馈增删修改
- **skill 不存在** → 按模板结构 + 用户反馈从头生成

写完后展示关键改动，确认后写入 `.claude/skills/verifier-<surface>/SKILL.md`。

### 3.5. 定制 TEST.md 人工清单

所有表面 skill 处理完后，检查并定制人工验证清单。

#### 读当前 TEST.md

```bash
test -f "TEST.md" && echo "FOUND" || echo "NOT_FOUND"
```

- **不存在** → 说明项目没有 TEST.md，询问用户是否需要创建一个（跳转到生成步骤）
- **存在** → 读取内容

#### 分析项目结构，识别人工验证点

根据项目结构推导需要人眼确认的检查项：

- **Web 项目**（有 `templates/`、`server/`、路由定义）→ 关键页面 URL 路径
- **Desktop GUI**（有 `desktop/`、`Cargo.toml` 含 gui 依赖）→ 托盘菜单、设置窗口、启动/停止流程
- **Unity 项目**（有 `Assets/`、`.unity` 场景文件）→ 画面表现、UI 布局、Play Mode 交互

#### 展示并确认

```
## TEST.md 人工清单定制

当前 TEST.md 内容如上。我根据项目结构推导出以下建议：

**关键页面（需人工检查）**:
- / — 首页/概览：图表渲染、数据加载
- /settings — 设置页：表单交互、保存功能
- /tasks — 任务页：列表显示、状态切换

**其他人工验证项**:
- Desktop GUI: 托盘右键菜单、设置面板渲染、窗口关闭不退出

请确认（直接按回车跳过此步骤，保留现有 TEST.md）：
- 需要改什么？增/删/改哪些检查点？
```

#### 写入

根据用户反馈修改 TEST.md 内容后写回项目根目录。

### 4. 删除无用 skill

检查 `.claude/skills/verifier-*/`：
- 对应表面已被用户排除的 → 问用户是否删除
- 表面不存在且未被步骤 2 确认的 → 建议删除，用户确认后执行

### 5. 验证

最后逐条检查（实际 grep/读文件）：

1. `grep '<填写' .claude/skills/verifier-*/SKILL.md` → **必须无输出**（所有占位符已填充）
2. 每个 skill 包含全部 7 个必需章节：
   启动检查、使用方法、可用工具（或说明无）、验证原语、探测、清理、自更新
3. 每个 skill 每章都有内容（定制后不能有空章）
4. 每个原语 = 描述 + 命令 + 适用条件
5. 探测 = 通用项 + 至少一条项目特有探测
6. 启动命令和清理命令在当前环境可执行
7. TEST.md 已定制（如项目有此文件）：检查内容是否匹配项目实际结构

## 输出

```
## loop-verify-init 完成

### 处理的 skill
- verifier-web: ✅ 已定制（用户确认端口 8765，新增 /tasks 页面）
- verifier-api: ✅ 已定制（用户补充了 /tasks/list 端点校验）
- verifier-cli: ✅ 已生成（用户提供了完整的子命令列表）

### 删除的 skill
- verifier-desktop: 已删除（用户确认项目无 GUI）

### TEST.md
- ✅ 已定制（用户确认了 3 个关键页面和 Desktop GUI 交互检查点）

### 跳过的表面
- Unity MCP: 跳过（用户表示暂不需要）
```

## 禁止

- 不要跳过用户确认环节自己全部搞定
- 不要编造不存在的端点、命令或配置
- 不要在用户不同意时强行生成或删除 skill
- 不要一次展示太多信息——逐表面处理，每个确认完再下一个
