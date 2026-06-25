# Proposal: 优化 VERIFY.md / TEST.md 模板体系并新增 loop-test-init 技能

## Why

当前 VERIFY.md 和 TEST.md 模板存在几个问题：presets.py 中的结构化 verify.steps 从未被消费（verify.py 无外部调用方），属于死代码；三个 preset 的模板使用硬编码命令和占位符（如 `python -m <模块名>`），缺乏对项目实际情况的指导性描述；模板之间缺少统一的文档生命周期设计——环境准备、运行时验证、清理恢复等流程散落或不完整。此外没有机制帮助用户从"通用模板"过渡到"项目专属文档"。

## What Changes

- **删除** verify.py 及 presets.py 中各 preset 的 verify.steps 结构化数据（**BREAKING**：移除 `presets.apply_preset()` 中 verify steps 写入、`cli.py` 中 show 命令展示 verify steps、`settings.html` 中 verify steps badges 展示）
- **重写** VERIFY.md.j2 × 3：以自然语言指导性描述替代硬编码命令，基于真实参考项目（Python Server → loop-engineering，Unity → PVPProject7）提供具体例子和上下文。模板内容已定稿，见：
  - [templates/verify/python-server/VERIFY.md.j2](../../templates/verify/python-server/VERIFY.md.j2)
  - [templates/verify/unity-tolua/VERIFY.md.j2](../../templates/verify/unity-tolua/VERIFY.md.j2)
  - [templates/verify/generic/VERIFY.md.j2](../../templates/verify/generic/VERIFY.md.j2)
- **重写** TEST.md.j2 × 3：统一文档结构为"环境准备 → 启动 → 运行时验证 → 清理恢复 → 测试清单"，标注 🤖 verifier 已执行步骤，加入 worktree 环境恢复指引。模板内容已定稿，见：
  - [templates/verify/python-server/TEST.md.j2](../../templates/verify/python-server/TEST.md.j2)
  - [templates/verify/unity-tolua/TEST.md.j2](../../templates/verify/unity-tolua/TEST.md.j2)
  - [templates/verify/generic/TEST.md.j2](../../templates/verify/generic/TEST.md.j2)
- **Generic 模板**：移除 npm 硬编码，改为多语言（Node/Python/Go/Rust）参考表格，verifier 自动检测项目类型
- **占位符**：presets.py 中 test_serve 等字段空值处理——空值留空 + 模板渲染提示性文本而非无效占位符
- **新增** `loop-test-init` skill：理解项目 → 对照模板增删步骤 → 填充具体值 → 写回项目专属文档

## Capabilities

### New Capabilities

- `verify-doc-templates`: 验证文档模板系统，定义三个 preset（python-server、unity-tolua、generic）的 VERIFY.md 和 TEST.md 模板，包含指导性描述和参考示例
- `loop-test-init`: 初始化/完善项目测试文档的技能，读当前文档 + 扫描项目结构 + 填充具体值 + 增删定制步骤

### Modified Capabilities

无（未修改现有 spec 级别行为）。

## Impact

- `src/loop_engineering/verify.py` — 删除
- `src/loop_engineering/presets.py` — 删除 verify 块、精简 apply_preset()
- `src/loop_engineering/cli.py` — 删除 show 命令中 verify steps 展示、`_cmd_init` 调用路径
- `src/loop_engineering/server/templates/settings.html` — 删除 verify steps badges
- `src/loop_engineering.egg-info/SOURCES.txt` — 删除 verify.py 条目
- `templates/verify/*/VERIFY.md.j2` × 3 — 重写
- `templates/verify/*/TEST.md.j2` × 3 — 重写
- `.claude/skills/loop-test-init/SKILL.md` — 新增
