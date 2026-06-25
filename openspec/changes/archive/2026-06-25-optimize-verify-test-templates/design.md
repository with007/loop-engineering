# Design: 优化 VERIFY.md / TEST.md 模板体系

## Context

当前 verify.py 和 presets.py 中的结构化 verify.steps 代码存在但没有外部消费方。task-runner 的 verifier 子代理直接读 VERIFY.md（自然语言）执行验证，而非读取 verify.steps 结构化配置。这造成了双套表示——维护 presets.py 的步骤定义和模板中的手写步骤描述，且无同步机制。

模板本身使用硬编码命令（如 `npm run build`）和无意义占位符（如 `python -m <模块名>`），缺少针对项目实际情况的指导性描述。TEST.md 缺少环境准备、运行时验证、清理恢复等完整测试生命周期指引。

参考项目：
- Python Server → loop-engineering 自身（FastAPI + CLI 工具，无 pytest 测试）
- Unity + ToLua → PVPProject7（MCP refresh_unity、genLuaPath.py、runtime-test skill）

## Goals / Non-Goals

**Goals:**
- 删除 verify.py 及相关死代码，消除 DRY 问题
- 模板使用自然语言指导性描述 + 具体示例，不硬编码命令
- TEST.md 覆盖完整测试生命周期：环境准备 → 启动 → 运行时验证 → 清理恢复
- 标注 🤖 verifier 已执行步骤，避免人机重复
- Generic 模板移除 npm 硬编码，改为多语言参考表格
- 新增 loop-test-init skill：理解项目 → 定制文档

**Non-Goals:**
- 不合并三个 preset 的模板为一个（保持独立以支持定制化）
- 不添加时间戳/版本号（git 已解决变化追踪）
- 不加 VERIFY.md ↔ TEST.md 交叉引用
- 不修改 task-runner / task-merge 的框架级验证逻辑

## Decisions

### 1. 删除 verify.py 和 presets verify.steps

verify.py 定义了 `read_pipeline()`、`run_pipeline()`、`run_step()` 和 7 种 step type（shell, npm_build, npm_test, go_build, go_test, unity_refresh, lua_test）。整个文件无外部 import。presets.py 中每个 preset 的 `"verify": {"steps": [...]}` 块同样无外部消费方（仅 `cli.py` show 命令和 `settings.html` badges 展示用）。

**清理范围**：
- `src/loop_engineering/verify.py` — 整个文件
- `src/loop_engineering/presets.py` — 删除 `PRESETS["verify"]` 块、`apply_preset()` 中 verify steps 写入逻辑
- `src/loop_engineering/cli.py:322-329` — show 命令中展示 verify steps 的代码
- `src/loop_engineering/server/templates/settings.html:75-82` — verify steps badges
- `src/loop_engineering.egg-info/SOURCES.txt` — verify.py 条目

`apply_preset()` 保留 `config["type"]` 设置逻辑（被 CLI 和 Web API 使用）。

### 2. 模板指导性描述风格

不引入特殊标记语法（如 `<!-- GUIDE: -->` 注释或 `🤖` 标记）。使用自然语言段落直接描述：告诉人这步干什么、常见选项是什么、verifier 没配置时会怎么处理。

参考真实项目（而不是抽象框架名）：
- Python Server 参考 loop-engineering：`pip install -e ".[ui]"`、`loop ui start`、pytest
- Unity 参考 PVPProject7：`genLuaPath.py`、`DotsTest.lua`、`config.json` 调试开关

### 3. TEST.md 文档结构

所有 preset 统一使用四阶段结构：

```
## 环境准备          → 安装依赖、检查配置
## 启动项目          → 启动命令 + 🤖 标注
## 运行时验证        → 人类验证 verifier 做不到的事
## 测试完成后        → 停服务 + 恢复 worktree 环境
## 测试清单          → preset 预设场景（可编辑）
```

Python Server 特有的清理恢复：切回主 worktree 重新 `pip install`，避免 agent worktree 安装的依赖污染主环境。Generic 则提供多语言参考表格。

### 4. VERIFY.md 步骤设计

| 步骤 | Python | Unity | Generic |
|------|:------:|:-----:|:-------:|
| 构建检查 | — | — | 参考表 (npm/go/cargo) |
| 测试运行 | pytest 等 | — | 参考表 (pytest/go test等) |
| 编译检查 | — | MCP refresh_unity | — |
| Lua 路径生成 | — | genLuaPath.py | — |
| Lua 运行时测试 | — | runtime-test skill | — |
| 代码逻辑检查 | ✅ | ✅ | ✅ |
| 模板检查 | ✅ | — | — |
| 运行时验证 | ✅ curl/WebFetch | — | ✅ |

代码逻辑检查保留在所有 preset 中（正确性的底线验证）。运行时验证在 Python Server 和 Generic 中为 verifier 自动执行（后台启动服务 → curl/WebFetch → 停止），Unity 中通过 MCP 在 VERIFY.md 的编译/测试步骤中已覆盖。

框架级通用验证（读 diff、确认变更范围、无多余文件）不出现在 VERIFY.md 中，由 task-runner SKILL.md 统一处理。

### 5. 占位符：源头修

presets.py 中 `test_serve` 等字段空值时不写占位符（如 `"python -m <模块名>"`）。空值 → 模板渲染提示性文本，如 "填写项目的启动命令"。

### 6. loop-test-init skill

一个 Claude Code skill（`.claude/skills/loop-test-init/SKILL.md`），行为：

1. **理解项目**：读代码结构、入口点、依赖、现有 VERIFY.md / TEST.md
2. **对照模板**：判断哪些指导性步骤适用、哪些多余；发现项目有但模板未覆盖的流程（如 Docker、CI、数据库迁移）决定是否新增
3. **填充具体值**：将指导性描述替换为项目实际命令和参数
4. **写回**：生成项目专属的 VERIFY.md 和 TEST.md

交互模式为 AI 驱动——skill 在 Claude Code 上下文中执行，靠 AI 能力理解项目并做决策，不需要确定性规则引擎。

## Risks / Trade-offs

- **[模板修改后旧项目重新 `loop setup`]**: 旧项目如果重新运行 setup，模板内容会变化。模板头部的覆盖警告告知用户。→ 建议用户在 setup 后用 loop-test-init 定制化，定制后避免再次 setup 覆盖。
- **[指导性描述可能让 AI verifier 困惑]**: 模板混合了指导性描述和实际指令。→ verifier 自己判断哪些是通用建议哪些是已填写的具体值，和模板渲染前一样。已在 task-runner SKILL.md 中定义了通用验证逻辑作为兜底。
- **[loop-test-init 依赖 AI 判断项目结构]**: 不同项目结构差异大，AI 可能误判。→ skill 提示中要求"先深入理解项目"，且只做增量修改（不覆盖用户已填的值）。
