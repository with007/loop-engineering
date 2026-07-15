# Verify Doc Templates

验证文档模板系统，定义项目特定验证步骤和手动测试指南的模板结构。

## Purpose

为不同项目类型（Python Server、Unity + ToLua、Generic）提供 VERIFY.md 和 TEST.md 的 Jinja2 模板，包含自然语言指导性描述和参考示例。模板由 `loop setup` 渲染到项目根目录，verifier 子代理和人类用户分别使用。

## Requirements

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
