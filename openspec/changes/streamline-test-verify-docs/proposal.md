## Why

VERIFY.md 的验证方法论已被 `loop-verify` (agent) + `verifier-*` (表面命令) skills 体系完全吸收，文件本身成为冗余。TEST.md 中"怎么自动化测试"的部分同样与 verifier-* skills 重复，真正对 task-merge 人工复核门禁有价值的是"人眼判断什么"。同时 `loop-test-init` 原本负责定制两个文档，现在 VERIFY.md 退役、TEST.md 瘦身，其存在理由消失。合并、精简、去重。

## What Changes

- **BREAKING**: 删除 VERIFY.md.j2 × 3 模板和所有已部署的 VERIFY.md 产物
- **BREAKING**: 删除 loop-test-init skill (模板和部署产物)
- 精简 TEST.md.j2 × 3 模板为纯人工检查清单 (环境准备/启停命令移至 verifier-* skills)
- 在 loop-verify-init 中加入 TEST.md 人工清单定制步骤
- task-merge Step 3 重写: 调用 loop-verify 做自动验证(可跳过) → 从 verifier-* skills 取环境命令 → 从 TEST.md 取人工检查清单 → pass/fail
- setup.py 删 loop-test-init 部署逻辑，调整 TEST.md 渲染变量
- CLAUDE.md §4 更新定位说明
- settings 页模板预览删 VERIFY.md 选项
- 删除 `docs.py` 中 VERIFY.md 相关代码

## Capabilities

### New Capabilities
<!-- None — this change modifies existing capabilities -->

### Modified Capabilities
- `verify-doc-templates`: 删除 VERIFY.md 模板定义, TEST.md 模板从完整测试指南精简为纯人工检查清单
- `loop-test-init`: 废弃并删除，人工清单定制合并入 loop-verify-init

## Impact

- `templates/verify/*/VERIFY.md.j2` × 3 — 删除
- `templates/verify/*/TEST.md.j2` × 3 — 重写
- `templates/skills/task-merge/SKILL.md.j2` — Step 3 重写
- `templates/skills/loop-test-init/SKILL.md.j2` — 删除
- `templates/skills/loop-verify-init/SKILL.md.j2` — 新增 TEST.md 定制步骤
- `openspec/specs/loop-test-init/spec.md` — 归档
- `openspec/specs/verify-doc-templates/spec.md` — 更新
- `CLAUDE.md` §4 — 更新
- `src/loop_engineering/setup.py` — 删 loop-test-init 部署 + 调整 TEST.md 渲染
- `src/loop_engineering/server/api/docs.py` — 删 VERIFY.md 相关代码
- `templates/verify/python-server/settings.html` (如有) — 删 VERIFY.md badge/引用
- 各项目根目录下的 VERIFY.md (部署产物) — 删除
- `.claude/skills/task-merge/SKILL.md` — 重新生成
