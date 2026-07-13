## MODIFIED Requirements

### Requirement: TEST.md template structure

项目根目录的 TEST.md SHALL 由 `loop setup` 根据项目类型 preset 从 Jinja2 模板生成，
定义人工验证检查清单。

模板 SHALL 包含：
- 人工验证定位说明（自动化验证由 loop-verify + verifier-* skills 处理）
- 关键页面的 URL 路径和人工检查点（图表渲染、元素显示、交互流程等）
- 模块人工验证示例（Desktop GUI 交互、浏览器视觉检查等 loop-verify 无法自动判断的部分）

模板 SHALL NOT 包含：
- 自动化测试工具列表（curl、WebFetch、CLI 等 — 这些在 verifier-* skills 中）
- 环境准备/启动/停止/恢复命令（这些在 verifier-* skills 中）
- API 端点验证方式、CLI 验证方式（由 loop-verify 通过 verifier-* 自动执行）
- 🤖 verifier 标注（verifier 概念已被 loop-verify 替代）

#### Scenario: Python Server TEST.md contains only manual checklist

- **WHEN** 对 Python Server 项目运行 `loop setup`
- **THEN** 生成 TEST.md 包含关键页面 URL 和人工检查点
- **AND** 不包含 pip install、curl、loop ui start 等自动化命令

#### Scenario: Unity TEST.md focuses on visual verification

- **WHEN** 对 Unity 项目运行 `loop setup`
- **THEN** 生成 TEST.md 包含画面表现、帧率、UI 交互等人眼验证项
- **AND** 不包含 refresh_unity、read_console、runtime-test 等 MCP 命令

#### Scenario: Generic TEST.md includes multi-language hints

- **WHEN** 对未指定类型的项目运行 `loop setup`
- **THEN** 生成 TEST.md 包含通用的人工检查指引
- **AND** 不包含特定语言的构建/测试命令

## REMOVED Requirements

### Requirement: VERIFY.md template structure

**Reason**: VERIFY.md 的方法论（表面识别、触发变更、边界探测、报告格式）已被 loop-verify SKILL.md 完全吸收；表面命令（启动、就绪检查、清理）已迁移到 verifier-* skills。保留两套表示造成维护负担且无消费者。

**Migration**: 之前读 VERIFY.md 的 verifier 子代理改用 loop-verify skill。需要验证方法论文档的开发者直接阅读 loop-verify SKILL.md 或运行 loop-verify。

### Requirement: Template variables and placeholder handling

**Reason**: `get_verify_template_vars()` 从 preset 配置提取变量主要用于 VERIFY.md 模板渲染。TEST.md 模板精简后只需 `project_name`，不再需要复杂的变量提取逻辑。

**Migration**: `deploy_verify_docs()` 直接使用 `project_name` 渲染 TEST.md.j2，不需要 `get_verify_template_vars()`（如还有此函数则删除）。

### Requirement: Dead code removal

**Reason**: 此 Requirement 描述的是 2026-06-25 已完成的历史清理（删除 verify.py、presets.py 中的 verify 块等）。作为 spec 快照保留，不再对应当前或未来的工作项。

**Migration**: 无需迁移，相关代码已在上次清理中删除。
