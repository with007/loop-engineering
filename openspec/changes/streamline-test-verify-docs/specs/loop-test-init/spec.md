## REMOVED Requirements

### Requirement: Skill reads current docs and project context

**Reason**: loop-test-init skill 被删除。VERIFY.md 退役，TEST.md 精简为纯人工清单后定制需求大幅减少，剩余的 TEST.md 定制逻辑并入 loop-verify-init 的 Step 3.5。

**Migration**: 需要初始化或更新 verifier skills + 人工清单的用户运行 `/loop-verify-init`。该 skill 会同时处理 verifier-* skills 和 TEST.md 的定制。

### Requirement: Skill identifies guidance vs filled content

**Reason**: 同上，skill 删除后此需求不再适用。loop-verify-init 有自己的定制确认流程（逐表面与用户交互），不依赖"指导性描述 vs 已填充"的判断逻辑。

**Migration**: loop-verify-init 通过用户交互确认内容，而非自动判断默认值。

### Requirement: Skill fills concrete values and customizes steps

**Reason**: 同上。TEST.md 精简后不再包含需要填充的命令行占位符（环境准备、启动、API 验证等已移到 verifier-*），人工检查清单的定制更多是增删检查项而非填充占位符。

**Migration**: loop-verify-init Step 3.5 分析项目结构后展示人工检查点建议，用户确认/修改后写入。

### Requirement: Skill persists customized docs

**Reason**: 同上。loop-verify-init 在完成所有表面处理和 TEST.md 定制后统一写回文件。

**Migration**: loop-verify-init 保持"展示改动 → 用户确认 → 写入文件"的模式。
