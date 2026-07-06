# Loop Engineering — Claude Rules

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## 1. Bug 修复流程

如果是报错/bug 而不是新需求，**不要直接开始修改代码**。流程：

1. **先加日志，不要猜**。在关键路径打点：入口、出口、分支条件、中间值。对于没有 console 的 GUI 应用（如 `#![windows_subsystem = "windows"]`），日志写到文件并用 `flush()` 确保落盘。
2. 拿日志数据定位根因。日志应能回答："代码走到了哪一步？哪个条件分支没进？哪个值不符合预期？"
3. 告诉用户：发现了什么问题、是什么原因导致的、日志如何证明
4. 说明打算怎么修复
5. 用户确认后再动手

**禁止**在没有日志数据的情况下来回猜测、反复修改同一段代码。如果改了 3 次还没解决，停下来加日志。

### 日志文件路径

不同场景的日志在不同位置，排查问题时先对照此表找到正确文件：

| 场景 | 日志路径 | 说明 |
|------|----------|------|
| **Desktop 生产环境**（用户通过安装包安装） | `%LOCALAPPDATA%/LoopDashboard/dashboard.log` | 主日志，包含 Rust 侧所有事件（启动、菜单、更新检查、下载进度、心跳等） |
| **Desktop 开发构建**（`cargo build --release`） | `desktop/target/release/dashboard.log` | 开发/测试时的日志，与生产环境格式相同 |
| **Desktop 生产环境 — Python 子进程** | `%LOCALAPPDATA%/LoopDashboard/app/src/loop_engineering/server/dashboard.log` | uvicorn 服务器进程的日志（Python 侧 `_log()` 输出） |
| **Desktop 开发构建 — Python 子进程** | `desktop/target/release/app/src/loop_engineering/server/dashboard.log` | 与上面路径对应，开发构建中 Python server 的输出 |
| **Web 仪表盘**（`loop ui start`） | 终端 stdout/stderr | 无文件日志，直接在终端查看 |
| **Claude Code 会话** | 终端输出 | Claude Code 的输出直接在终端 |

> 所有 Desktop 日志都用 `chrono_now()` 打时间戳（Unix 秒 + 毫秒），用 `f.flush()` 确保每条立即落盘。查找关键事件时用 `grep` 筛选关键词（如 `update:`、`user_event:`、`menu:`、`heartbeat:`、`settings:` 等）。

## 2. 测试必须贴近真实场景

修改完代码之后，**必须用和生产环境一致的方式跑通测试**。

### 原则

- 测试要用**实际生产中的命令、进程、数据和流程**，不是能跑通的简化版
- **GUI 应用的测试不能只靠发 `SendMessage` 绕过真实交互路径**。如果真实路径是"右键托盘 → 弹出菜单 → 点击菜单项"，测试也要走这个完整路径，不能直接 `PostMessage(WM_COMMAND)` 绕过前面的步骤
- 改了启动/停止/聚焦 loop 窗口的代码 → 必须启动真实 `claude --dangerously-skip-permissions` 进程来验证
- 改了 API 端点 → 调真实端点或直接调底层函数，验证返回值
- 改了模板 → 用真实模板文件渲染，检查关键字段

### 禁止

- 用 `echo` / `timeout` / `ping` 替代真实业务命令来"模拟"
- 用与生产不同的参数或环境来"方便测试"
- 只测 happy path 不测异常
- 绕过交互路径（如直接发 Windows 消息模拟点击，而不是实际触发完整用户操作链）

## 3. 模板修改规则

修改 Skill / Command / Config 时，**始终改模板源，不要改部署副本**。

### 源与副本

| 角色 | 路径 | 说明 |
|------|------|------|
| **模板源** | `templates/skills/<name>/SKILL.md` 或 `.j2` | 唯一可编辑的源 |
| **部署副本** | `.claude/skills/<name>/SKILL.md` | `loop setup` 自动生成，会被覆盖 |

- `.j2` 模板通过 Jinja2 渲染生成 `.md`（变量从 `loop-config.yaml` 读取）
- 裸 `.md` 模板直接拷贝
- 两种情况下部署副本都是**生成产物**，手动改会在下次 `loop setup` 时丢失

### 检查方法

修改模板源后，渲染并对比确认一致性：

```bash
python -c "
from jinja2 import Environment, BaseLoader
vars = {...}  # 从 setup.py 的 j2_vars 复制
env = Environment(loader=BaseLoader())
with open('templates/skills/<name>/SKILL.md.j2') as f:
    rendered = env.from_string(f.read()).render(**vars)
with open('.claude/skills/<name>/SKILL.md') as f:
    deployed = f.read()
print('OK' if rendered == deployed else 'DIFF')
"
```

### 禁止

- 不要直接编辑 `.claude/skills/`、`.claude/commands/` 下的文件
- 不要同时保留 `.j2` 和闲置 `.md`（用 `.j2` 就删 `.md`）

## 4. TEST.md / VERIFY.md 定位

`TEST.md` 和 `VERIFY.md` 是**方法论参考**，不是必须全部执行的死清单。

- 文档自身已说明定位（"测试方法论参考"、"验证范围由变更驱动"）
- 使用方只需引用文档，按其中说明执行，不要重新解释文档定位
- 执行时：先理解变更范围，再从中选择涉及模块的手段，未涉及的跳过

## 6. 端到端开发测试闭环

GUI 应用（尤其是托盘/后台应用）的开发分两层测试：**自动化快速迭代** 和 **人工最终验证**。两层互补，不是替代。

### 第一层：自动化测试循环（开发阶段）

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  1. 写代码 + 加日志点                                     │
│       ↓                                                 │
│  2. 编译，启动应用                                        │
│       ↓                                                 │
│  3. 用 SendMessage/PostMessage 模拟用户操作               │
│     （发 WM_USER_TRAYICON 模拟右键，发 WM_COMMAND 模拟菜单点击）│
│       ↓                                                 │
│  4. 读日志，检查关键路径是否走到                             │
│       ↓                                                 │
│  5. 发现问题 → 修复 → 回到步骤 1                           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

这一步 Claude 可以独立完成，无需人工参与。日志确认所有关键路径走通后，进入第二层。

### 第二层：人工验证（发布前）

程序必须由用户实际操作一遍：右键托盘、点击菜单项、打开/关闭设置面板、点 X 关闭、托盘退出。确认：
- 无空白窗口
- 菜单即时响应（无巨量延迟）
- 设置面板正确渲染
- 关闭窗口不退出应用
- 退出正常终止进程

### 角色分工

| 角色 | 第一层（开发） | 第二层（验证） |
|------|-------------|-------------|
| Claude | 写代码、编译、模拟事件、读日志、修复 | 分析用户反馈的日志 |
| 用户 | — | 执行真实 GUI 操作、提供日志 |

### 快速测试 exe 修改

只改 exe 行为（对话框、进度条、日志、菜单等），**不用发版**。直接替换安装目录的 exe 重启即可：

```bash
# 编译
cargo build --release -p loop-dashboard

# 找到安装目录的 exe（如果用 Setup.exe 装在 Velopack 结构里，exe 在 current/ 下）
cp target/release/loop-dashboard.exe "$LOCALAPPDATA/LoopDashboard/current/loop-dashboard.exe"

# 右键托盘 → 退出 → 重启
```

发版（tag push → CI）只在测试**端到端更新流程**（下载 .nupkg → 弹框 → 应用 → 重启升级）时才需要。而且此时只需发**一个**新版作为"下载目标"，当前版本用本地替装 exe 的方式部署，不需要为修一个 bug 连发多个版本。

### 日志要求

- 每个关键路径必须有日志：入口、出口、条件分支、接收到的值
- 时间戳精确到毫秒，能计算帧间隔和响应延迟
- 日志写文件 + `flush()`，确保 crash 前数据不丢

### 禁止

- 第一层没通过就进入第二层——先让自动化测试跑通
- 用 API 模拟代替真实交互来"证明"最终效果——模拟只能用于开发迭代
- 在用户测试前宣称"已经好了"——只有第二层确认后才能下结论

## 7. 方法论持续迭代

以上规则（1-6）不是一成不变的。每次遇到新的问题模式或开发痛点，**更新对应的规则章节**，把经验固化。

- 发现了新的框架限制 → 更新第 5 节
- 测试方法有改进 → 更新第 2 节或第 6 节
- 日志策略有优化 → 更新第 1 节
- 禁止项有新增 → 更新对应章节的"禁止"列表

每次规则更新应附带具体案例（本次对话中发生了什么），让规则有据可查。

## 8. Git 操作规则

本机已配置 Windows OpenSSH Agent + `D:/key/bwd` 密钥对（对应 GitHub `with007` 账户）。

### 默认 SSH

Git Bash (MinGW) 的 SSH agent 与 Windows 的不互通。使用 Windows 原生 SSH 来复用系统密钥：

```bash
git config --global core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"
```

已全局配置，所有 `git push/pull/fetch` 直接可用。

### 发布流程

**默认走 CI，不在本地打包**。`.github/workflows/release.yml` 会在 tag 推送后完整执行 cargo build + vpk pack + 上传 release assets。本地 `release.py` 只在 CI 不可用时作为备选。

| 步骤 | 命令 | 谁做 |
|------|------|------|
| 1. 写 CHANGELOG | 在 `CHANGELOG.md` 顶部加 `## v0.1.x` 段落 | Claude |
| 2. 预 bump 版本号 | 改 `desktop/Cargo.toml` + `desktop/version.txt` 为新版本 | Claude |
| 3. 提交 + 打 tag + 推送 | `git commit && git tag v0.1.x && git push origin master && git push origin v0.1.x` | Claude |
| 4. CI 构建打包发布 | GitHub Actions `release.yml`（tag `v*` 触发） | 自动 |

> **关键：必须先 commit 版本号 bump 再推 tag。** `release.py` 里 `build_rust()` 在 `write_version()` 之前执行，CI checkout 出来的 `Cargo.toml` 版本号就是 exe 的 `CARGO_PKG_VERSION`（用于更新检查比对）。不预 bump 会导致打出来的 exe 版本号是上一个版本，更新检查永远找不到新版。
>
> **案例（2026-07-03）**：发布 v0.1.12 时先本地跑 `release.py` 再推 tag，本地产物 exe 仍是 0.1.11（build_rust 跑在 bump 前），白干且产物错误。改为"改版本号 → commit → tag → push → CI 构建"后，CI checkout 的 Cargo.toml 已是 0.1.12，构建正确。

备选（CI 不可用时）：`python packaging/release.py 0.1.x --publish` 本地构建+发布。

### 令牌

- 发布 token：通过环境变量 `GITHUB_TOKEN` 或 `gh auth token` 获取（不再硬编码）
- 更新检查：公开仓库不需要 token

仓库：`git@github.com:with007/loop-engineering.git`

### 发版流程

```bash
# 1. 写 CHANGELOG.md（在顶部加 ## v0.1.7 段落）
# 2. 预 bump 版本号
#    编辑 desktop/Cargo.toml 的 version = "0.1.7"
#    编辑 desktop/version.txt 为 0.1.7
# 3. 提交 + 打 tag + 推送（CI 自动构建打包发布）
git add CHANGELOG.md desktop/Cargo.toml desktop/version.txt
git commit -m "chore: bump to v0.1.7"
git tag v0.1.7
git push origin master
git push origin v0.1.7
```

- **CI 不可用时的备选**：`python packaging/release.py 0.1.7 --publish`（本地构建+发布，需 `GITHUB_TOKEN`）
- **自动递增**：版本号填 `auto` 自动 `0.1.0 → 0.1.1`
- **VSCode**：`Ctrl+Shift+P` → `🚀 Release + Publish` → 输版本号
- **CI 触发**：push tag `v*` 或 GitHub Actions 网页手动触发
