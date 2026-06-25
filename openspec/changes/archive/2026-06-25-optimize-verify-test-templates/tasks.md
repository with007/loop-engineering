# Tasks: 优化 VERIFY.md / TEST.md 模板体系

## 1. 删除死代码

- [x] 1.1 删除 `src/loop_engineering/verify.py`
- [x] 1.2 删除 `presets.py` 中各 preset 的 `"verify"` 块（保留 `"test"` 块）
- [x] 1.3 精简 `presets.py` 的 `apply_preset()` — 删除 `config["verify"]["steps"]` 写入，保留 `config["type"]` 设置
- [x] 1.4 删除 `cli.py` show 命令中展示 verify steps 的代码段
- [x] 1.5 删除 `settings.html` 中 verify steps badges 展示的 HTML 块
- [x] 1.6 更新 `src/loop_engineering.egg-info/SOURCES.txt` 移除 verify.py 条目

## 2. Python Server 模板

- [x] 2.1 重写 `templates/verify/python-server/VERIFY.md.j2` — 4 步验证（测试运行、代码逻辑检查、模板检查、运行时验证），自然语言指导 + 参考示例
- [x] 2.2 重写 `templates/verify/python-server/TEST.md.j2` — 4 阶段（环境准备、启动、运行时验证、清理恢复），🤖 标注 verifier 步骤，worktree pip install 恢复指引

## 3. Unity + ToLua 模板

- [x] 3.1 重写 `templates/verify/unity-tolua/VERIFY.md.j2` — 4 步验证（编译检查、Lua 路径生成、Lua 运行时测试、代码逻辑检查），引用 PVPProject7 作为参考
- [x] 3.2 重写 `templates/verify/unity-tolua/TEST.md.j2` — 4 阶段结构，运行时验证聚焦视觉检查（verifier 的编译/Console/Lua 测试已覆盖），config.json 开关恢复

## 4. Generic 模板

- [x] 4.1 重写 `templates/verify/generic/VERIFY.md.j2` — 移除 npm 硬编码，改为多语言参考表格，4 步验证
- [x] 4.2 重写 `templates/verify/generic/TEST.md.j2` — 多语言环境准备/清理恢复表格，4 阶段结构

## 5. Presets 配置清理

- [x] 5.1 清理 `presets.py` 中 `test_serve` 等字段的占位符值
- [x] 5.2 确认 `get_verify_template_vars()` 返回的变量覆盖所有模板中使用的字段

## 6. loop-test-init skill

- [x] 6.1 创建 `.claude/skills/loop-test-init/SKILL.md` — skill 定义文档
- [x] 6.2 skill 流程：理解项目 → 读当前文档 → 区分指导性描述和已填值 → 填充具体值 → 增删步骤 → 写回

## 7. 验证

- [x] 7.1 删除 dead code 后确认 `loop setup` 功能正常（模板渲染和文件写入无报错）
- [x] 7.2 对 Python Server 项目运行 `loop setup`，检查生成的 VERIFY.md 和 TEST.md 内容
- [x] 7.3 对 Unity + ToLua 项目运行 `loop setup`，检查生成内容
- [ ] 7.4 测试 `/loop-test-init` skill 对 loop-engineering 项目的定制效果（需在 Claude Code 会话中手动执行）
