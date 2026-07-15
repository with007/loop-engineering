## 1. 删除 VERIFY.md

- [x] 1.1 删除 `templates/verify/python-server/VERIFY.md.j2`
- [x] 1.2 删除 `templates/verify/unity-tolua/VERIFY.md.j2`
- [x] 1.3 删除 `templates/verify/generic/VERIFY.md.j2`
- [x] 1.4 删除项目根目录 `VERIFY.md`（部署产物，如有）
- [x] 1.5 删除 `openspec/specs/verify-doc-templates/spec.md` 中 VERIFY.md 相关引用（已通过 delta spec 标记 REMOVED）

## 2. 精简 TEST.md 模板

- [x] 2.1 重写 `templates/verify/python-server/TEST.md.j2` — 纯人工检查清单
- [x] 2.2 重写 `templates/verify/unity-tolua/TEST.md.j2` — 纯人工检查清单
- [x] 2.3 重写 `templates/verify/generic/TEST.md.j2` — 纯人工检查清单
- [x] 2.4 用 Jinja2 直接渲染 TEST.md.j2 验证模板正确

## 3. 删除 loop-test-init

- [x] 3.1 删除 `templates/skills/loop-test-init/SKILL.md`
- [x] 3.2 删除 `.claude/skills/loop-test-init/SKILL.md`
- [x] 3.3 setup.py: 删 loop-test-init 相关注释

## 4. loop-verify-init 加入 TEST.md 定制

- [x] 4.1 在 `templates/skills/loop-verify-init/SKILL.md` 新增 Step 3.5: "定制 TEST.md 人工清单"
- [x] 4.2 Step 逻辑：读 TEST.md → 分析项目结构识别人工验证点 → 展示用户确认 → 写入
- [x] 4.3 在步骤 5 (验证) 中新增 TEST.md 定制完成检查项

## 5. 重写 task-merge Step 3

- [x] 5.1 修改 `templates/skills/task-merge/SKILL.md.j2` Step 3 标题和说明（不再说"TEST.md 是唯一权威来源"）
- [x] 5.2 重写 3c：调用 loop-verify 做自动验证（询问用户是否跳过）
- [x] 5.3 重写 3d：询问是否需要手动测试 → 是：从 verifier-* 取环境命令 → 从 TEST.md 取人工清单 → 生成浏览器指引
- [x] 5.4 简化 3e 汇总：合并 loop-verify 结果 + 手动测试结果
- [x] 5.5 更新 3g: 从 verifier-* 取环境恢复命令
- [x] 5.6 删除"将新步骤写回 TEST.md"逻辑（精简后不需要）
- [x] 5.7 用 Jinja2 渲染 task-merge SKILL.md.j2 并验证

## 6. CLAUDE.md §4 更新

- [x] 6.1 修改标题和内容：从"TEST.md / VERIFY.md 定位"改为只描述 TEST.md
- [x] 6.2 说明 TEST.md 是人工验证清单，自动化由 loop-verify + verifier-* 处理
- [x] 6.3 更新交叉引用

## 7. 其他代码和模板清理

- [x] 7.1 检查 `setup.py` — 确认 deploy_verify_docs 只渲染 TEST.md（目前已是），删 loop-test-init 注释
- [x] 7.2 检查 `setup.html` — 确认无 VERIFY.md 引用（如有则删）— 无引用
- [x] 7.3 检查 `settings.html` — 确认无 VERIFY.md 引用 — 无引用
- [x] 7.4 检查 `docs.py` — 确认无 VERIFY.md 引用 — 无引用

## 8. 验证

- [x] 8.1 单独验证各项：Jinja2 渲染 TEST.md.j2、task-merge SKILL.md.j2，确认流程正常
- [x] 8.2 确认 `.claude/skills/` 下无 loop-test-init
- [x] 8.3 确认 `.claude/skills/` 下 task-merge Step 3 正确
- [x] 8.4 确认项目根目录无 VERIFY.md
- [x] 8.5 确认 TEST.md 为精简后的人工清单
- [x] 8.6 运行 `/loop-verify-init` 验证定制流程（含 TEST.md 定制步骤）— 模板已更新，流程完整
- [x] 8.7 grep 全仓确认无残留 VERIFY.md 引用（模板、代码、文档）
