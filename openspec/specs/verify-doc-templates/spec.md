# Verify Doc Templates

验证文档模板系统，定义项目特定验证步骤和手动测试指南的模板结构。

## Purpose

为不同项目类型（Python Server、Unity + ToLua、Generic）提供 VERIFY.md 和 TEST.md 的 Jinja2 模板，包含自然语言指导性描述和参考示例。模板由 `loop setup` 渲染到项目根目录，verifier 子代理和人类用户分别使用。

## Requirements

### Requirement: VERIFY.md template structure

项目根目录的 VERIFY.md SHALL 由 `loop setup` 根据项目类型 preset 从 Jinja2 模板生成，
定义 verifier 子代理的自动化验证步骤。

模板 SHALL 包含：
- 项目类型标识和 preset 来源说明
- 每条步骤的自然语言指导性描述，包含具体例子和参考项目上下文
- 步骤级命令字段，支持用户编辑
- 通用验证步骤（代码逻辑检查、运行时验证等）

模板 SHALL NOT 包含：
- 框架级通用验证指令（diff 审查、变更范围确认——由 task-runner 统一处理）
- 硬编码的特定语言命令（通用 preset 使用多语言参考表格）

#### Scenario: Python Server project setup generates VERIFY.md

- **WHEN** 用户对 Python Server 项目运行 `loop setup`
- **THEN** 生成 VERIFY.md 包含测试运行、代码逻辑检查、模板检查、运行时验证四个步骤
- **AND** 每条步骤包含 pytest/unittest/tox 等参考示例和说明文本

#### Scenario: Unity ToLua project setup generates VERIFY.md

- **WHEN** 用户对 Unity + ToLua 项目运行 `loop setup`
- **THEN** 生成 VERIFY.md 包含编译检查、Lua 路径生成、Lua 运行时测试、代码逻辑检查四个步骤
- **AND** 步骤引用 MCP refresh_unity、genLuaPath.py、runtime-test skill 作为参考

#### Scenario: Generic project setup generates VERIFY.md

- **WHEN** 用户对未指定类型的项目运行 `loop setup`
- **THEN** 生成 VERIFY.md 包含构建检查、测试运行、代码逻辑检查、运行时验证四个步骤
- **AND** 每步包含 Node/Python/Go/Rust 多语言参考表格

### Requirement: TEST.md template structure

项目根目录的 TEST.md SHALL 由 `loop setup` 根据项目类型 preset 从 Jinja2 模板生成，
定义手动测试指南。

模板 SHALL 包含统一的四阶段结构：
1. 环境准备（安装依赖、检查配置）
2. 启动项目（启动命令 + verifier 已执行标注）
3. 运行时验证（人类验证 verifier 无法判断的部分）
4. 测试完成后（停止服务 + worktree 环境恢复）

模板 SHALL 使用 🤖 标注 verifier 已自动执行的步骤，告知用户可跳过或仅复核。

#### Scenario: Python Server TEST.md includes worktree cleanup

- **WHEN** 对 Python Server 项目生成 TEST.md
- **THEN** 测试完成后章节包含切回主 worktree 重新 pip install 的指引
- **AND** 标注 veifier 已自动执行 pip install、启动服务、请求端点

#### Scenario: Unity TEST.md focuses on visual verification

- **WHEN** 对 Unity 项目生成 TEST.md
- **THEN** 运行时验证章节只关注 verifier 无法判断的内容（画面表现、帧率、UI 交互）
- **AND** 使用文字说明编译检查、Console error、Lua 自动测试已由 verifier 完成

### Requirement: Template variables and placeholder handling

`get_verify_template_vars()` SHALL 从 preset 配置中提取模板变量。

空值或未配置的字段 SHALL 导致模板渲染提示性文本而非无效占位符。
preset 配置 SHALL NOT 使用尖括号占位符（如 `<模块名>`）。

#### Scenario: Empty test_serve renders guidance

- **WHEN** preset 的 test_serve 为空
- **THEN** 模板渲染 "填写项目的启动命令" 及同类项目的参考示例
- **AND** 不给无意义的填充值

### Requirement: Dead code removal

`src/loop_engineering/verify.py` 整个文件 SHALL 被删除。

`presets.py` 中各 preset 的 `"verify"` 块 SHALL 被删除。
`apply_preset()` SHALL 保留 `config["type"]` 设置逻辑，删除 verify steps 写入。
`cli.py` show 命令中展示 verify steps 的代码 SHALL 被删除。
`settings.html` 中 verify steps badges 展示 SHALL 被删除。

#### Scenario: setup still works after removal

- **WHEN** 删除 verify.py 及相关代码后运行 `loop setup`
- **THEN** 流程正常完成，VERIFY.md 和 TEST.md 由 Jinja2 模板渲染生成
- **AND** apply_preset() 仍正确设置 config["type"]
