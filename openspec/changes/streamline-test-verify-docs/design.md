## Context

当前验证文档体系有两层冗余：

```
旧体系                              新体系
───────                            ──────
VERIFY.md (agent 操作手册)    →    已被 loop-verify + verifier-* skills 完全替代
TEST.md (手动测试指南)        →    自动化部分与 verifier-* 重复，人工部分仍有价值
loop-test-init (定制器)       →    VERIFY.md 退役后存在理由消失
```

`loop-verify` skill 包含完整的验证方法论（表面识别、触发变更、边界探测、报告格式），`verifier-*` skills 包含各表面的具体命令（启动、就绪检查、清理）。VERIFY.md 的两部分内容已被完全吸收。

TEST.md 则不同——它同时包含自动化和人工两部分。task-merge Step 3（合入前验证门禁）消费 TEST.md，但自动化部分（curl、CLI、API 验证）现在应该由 loop-verify 处理，task-merge 只需要人工判断部分。

## Goals / Non-Goals

**Goals:**
- 消除 VERIFY.md 及其模板（已完全被 skill 体系替代）
- TEST.md 精简为纯人工检查清单（不包含可用自动化执行的命令）
- 删除 loop-test-init，人工清单定制并入 loop-verify-init
- task-merge Step 3 重写：先调 loop-verify，再按需从 verifier-* 取环境命令、从 TEST.md 取人工清单

**Non-Goals:**
- 不改变 loop-verify 本身的逻辑和方法论
- 不改变 verifier-* skills 的结构
- 不改变 task-merge 除 Step 3 以外的流程
- 不改变 loop setup 的总体流程（只调整涉及 VERIFY.md / loop-test-init 的部分）

## Decisions

### 1. TEST.md 瘦身后的结构

**删掉的内容：**
- 测试工具表（curl、WebFetch、CLI、cargo 等——这些是 verifier-* 的领域）
- 环境准备命令（pip install、venv 等——在 verifier-* 的启动检查里）
- 启动/停止服务命令（在 verifier-* 的启动检查和清理里）
- API 端点验证方式（loop-verify 用 verifier-* 做）
- CLI 命令验证（同上）
- 测试后恢复命令（在 verifier-* 的清理里）
- 🤖 verifier 标注（verifier 概念已被 loop-verify 替代）

**保留的内容：**
- 关键页面 URL + 人工检查点（图表渲染、元素存在、交互流程）
- 模块人工验证示例（Desktop GUI 交互、浏览器视觉检查等 loop-verify 做不到的）
- 顶部说明：自动化由 loop-verify + verifier-* skills 处理，本文档专注人工复核

**模板变量:** 只保留 `project_name`，删除 loop-test-init 相关的定制占位符说明。

**理由:** TEST.md 和 verifier-* 不应维护重复的命令。task-merge 做手动测试时，环境命令从 verifier-* 取，人工检查清单从 TEST.md 取，各司其职。

### 2. task-merge Step 3 新流程

```
旧:
  3c. 读 TEST.md
  3d. 按 TEST.md 制定测试计划 → 执行自动测试 → 询问浏览器手动测试
  3e-g. 汇总 → pass/fail → 按 TEST.md 恢复

新:
  3c. 调用 loop-verify (询问用户是否跳过)
  3d. 询问是否手动测试
      ├─ 否 → 跳到 3f
      └─ 是:
          ├─ 从 verifier-* skills 读取启动/就绪检查命令 → 执行
          ├─ 从 TEST.md 读取人工检查清单 → 生成浏览器指引
          ├─ 用户操作完成后:
          └─ 从 verifier-* skills 读取清理命令 → 执行
  3e. 汇总 loop-verify 结果 + 手动测试结果 → pass/fail
  3f-g. 不变
```

**关键变化:**
- "TEST.md 是唯一权威来源"→ 改为"verifier-* 提供环境命令，TEST.md 提供人工检查清单"
- TEST.md 不存在时不再跳过整个验证，只是跳过人工检查部分（loop-verify 仍然执行）
- 移除"将新步骤写回 TEST.md"的逻辑（精简后的 TEST.md 不需要频繁更新）

### 3. loop-verify-init 吸收人工清单定制

在 loop-verify-init 现有流程末尾"验证"检测之前，插入新步骤：

```
Step 3.5: 定制 TEST.md

读项目 TEST.md → 分析项目结构识别:
  - 关键页面 URL 路径（扫描 server/templates/*.html、路由定义等）
  - Desktop GUI 交互点（如有 desktop/ 目录）
  - 其他需要人眼验证的表面

→ 展示给用户确认（保留/修改/删掉/补充检查点）
→ 写入 TEST.md
```

**理由:** TEST.md 定制和 verifier-* 定制共享同一个"理解项目"阶段，合并在 loop-verify-init 中做避免重复分析。用户一次 `loop-verify-init` 同时完成 verifier skills 和人工清单的初始化。

### 4. VERIFY.md 删除范围

| 删除项 | 说明 |
|--------|------|
| `templates/verify/*/VERIFY.md.j2` × 3 | 模板源 |
| 项目根目录 `VERIFY.md` | 部署产物（手工删或 setup 时不生成） |
| CLAUDE.md §4 | 改为只描述 TEST.md 定位 |

不在删除范围：
- `docs.py` — 已经只处理 test 和 verifier-*，没有 VERIFY.md 引用
- `settings.html` — 同理，只有 TEST.md 编辑入口

**理由:** 实际上 setup.py 的 `deploy_verify_docs` 已经在遍历 `["TEST.md"]` 时跳过了 VERIFY.md（可能是之前某次改动遗留），所以主要工作是删模板文件和更新文档。

### 5. loop-test-init 删除

删除 `templates/skills/loop-test-init/SKILL.md`（模板）和 `.claude/skills/loop-test-init/SKILL.md`（部署产物）。对应 spec 归档。

### 6. templates/verify/*/skills/ 是否移动？

**决定: 不移动。** 当前 verifier skill 模板在 `templates/verify/<type>/skills/` 下，与 TEST.md.j2 同目录。这个路径虽然名称有"verify"字样（历史遗留），但语义上"templates/verify 目录存放与验证相关的模板（包括 surface skills 和人工清单）"仍然成立。

**备选方案（放弃）:** 将 skills 移到 `templates/skills/verifier-*/` 下。放弃原因：增加复杂度无实际收益，路径变动影响 setup.py 中的 verifier skill 部署逻辑和 docs API 中的模板预览逻辑。

## Risks / Trade-offs

- **TEST.md 过度精简** → 如果某个人工检查点对新用户不显而易见，可能会漏测 → 模板保留"模块人工验证示例"章节，提供足够上下文
- **task-merge 找不到 verifier-* skill** → 项目无 verifier-* skills 时无法获取环境命令 → 回退：提示用户手动安装依赖/启动服务，建议运行 loop-verify-init
- **loop-verify-init 变重** → 加入 TEST.md 定制后单次运行内容增多 → 保持逐步骤确认的交互模式，用户可跳过
