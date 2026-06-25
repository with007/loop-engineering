# Loop Test Init

初始化/完善项目测试文档的 Claude Code skill，将通用模板产物定制为项目专属文档。

## ADDED Requirements

### Requirement: Skill reads current docs and project context

`loop-test-init` skill SHALL 在执行时先深入理解项目：
- 读取项目根目录的 VERIFY.md 和 TEST.md 当前内容
- 扫描项目结构（入口点、依赖文件、测试框架、配置文件、模板文件）
- 理解项目类型、运行方式和技术栈

#### Scenario: Skill scans Python project and identifies test framework

- **WHEN** 用户在 loop-engineering 项目运行 `/loop-test-init`
- **THEN** skill 检测到 pyproject.toml、pytest 配置、FastAPI 入口点
- **AND** 读取当前 VERIFY.md 和 TEST.md 中的指导性描述内容

#### Scenario: Skill scans Unity project and identifies Lua test infrastructure

- **WHEN** 用户在 PVPProject7 运行 `/loop-test-init`
- **THEN** skill 检测到 config.json、genLuaPath.py、DotsTest.lua
- **AND** 识别 autoTestBattle 开关和 runtime-test skill 注册模式

### Requirement: Skill identifies guidance vs filled content

skill SHALL 区分模板生成的指导性描述和用户已填写的具体值。

判断逻辑：
- 当前值和模板默认值相同 → 尚未定制，可填充
- 当前值与模板默认值不同 → 用户已修改，保留不变
- 当前值含通用描述文本（非具体命令）→ 尚未定制

#### Scenario: User-edited test command is preserved

- **WHEN** 用户已手动将测试命令从 `python -m pytest` 改为 `tox`
- **THEN** skill 识别该值与模板默认值不同
- **AND** 保留 `tox` 不覆盖

### Requirement: Skill fills concrete values and customizes steps

skill SHALL 基于项目实际结构：
- 将指导性描述替换为项目具体命令和参数
- 删除不适用的步骤（如项目无模板文件则移除模板检查步骤）
- 新增模板未覆盖但项目需要的步骤（如 Docker 部署、数据库迁移、多语言构建等）
- 将 TEST.md 中的占位文本替换为实际启动命令、服务地址等

#### Scenario: Python project without templates removes template check

- **WHEN** 项目不包含 HTML/Jinja2 模板文件
- **THEN** skill 从 VERIFY.md 中移除 "模板检查" 步骤

#### Scenario: Skill adds Docker verification step

- **WHEN** 项目包含 Dockerfile 或 docker-compose.yml
- **THEN** skill 在 VERIFY.md 中新增构建/启动 Docker 镜像的验证步骤
- **AND** 步骤包含自然语言描述，保持文档可读性

### Requirement: Skill persists customized docs

skill SHALL 将定制完成的 VERIFY.md 和 TEST.md 写回项目根目录。
写回后指导性描述消失，替换为项目实际内容。
保留文档顶部的覆盖警告（告知 `loop setup` 会覆盖）。

#### Scenario: After skill completion

- **WHEN** skill 完成定制
- **THEN** VERIFY.md 和 TEST.md 包含项目专属命令和流程
- **AND** 不再包含通用指导模板文本
- **AND** 文件顶部保留覆盖警告
