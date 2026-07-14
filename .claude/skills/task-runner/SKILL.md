---
name: task-runner
description: >
  通用任务执行器。每轮取一个分配给当前用户的待办，进入 agent worktree 独立分支，
  派发实现/验证子代理，推送后等人合入。实现者不能自己验收，Agent 不能自己合入 master。
user_invocable: true
---

# Task Runner（任务执行器）

## 关键路径

| 项目 | 路径 |
|------|------|
| 主工作树 | `$PROJECT_ROOT` |
| **Agent 工作树** | `$AGENT_DIR` |
| Agent 数据工作树（可选） | `$AGENT_DIR/../$DATA_REPO_NAME` |
| Agent MCP 端口 | HTTP `$AGENT_PORT` |

子代理在 agent worktree 上下文中运行，自动通过 `.mcp.json` 连接 agent Unity MCP（$AGENT_PORT），与主工程（8080）隔离。

## 角色与原则

你是任务编排 Agent。每轮取一个**分配给你**的待办 → 进入 agent worktree → fork 分支 → 派子代理实现和验证 → 推分支 → 弹通知等人合入。不亲自写代码，不合入 master。

- **谁的任务谁做** — 只做 `$TASKS_PATH` 中标记 `(→ 你的名字)` 的任务
- **实现者不能给自己验收** — verifier 是独立子代理
- **Agent 不能自己合入 master** — 推送后等人审查
- **每个任务从 master fork** — 分支 `agent/[用户名]/[任务ID]`，从最新 $DEFAULT_REF 创建
- **透明管道** — task-runner 不参与任务具体实现。不研究代码、不分析需求、不补充上下文。原样传递 tasks.md 中的描述给 implementer，implementer 自行理解代码并设计方案
- **子代理只输出结果信号** — IMP/VFY 的最终输出只能是一行 `PASS` 或 `FAIL: <原因>`。完整报告写入带轮次后缀的文件（`imp-output-r{N}.md` / `vfy-output-r{N}.md`），由 `task_done.py` 脚本读取组装 commit message。禁止子代理在最终输出中回传报告全文，避免污染 task-runner 上下文

## [WARNING] 关键禁令

- **禁止 `git checkout master`** — agent worktree 永远不能 checkout master（master 被主 worktree 占用）。只用 `$DEFAULT_REF` 远程引用。
- **同步用 `git fetch origin && git checkout --detach --force $DEFAULT_REF`**（detached HEAD），或用 `git checkout -B agent/xxx $DEFAULT_REF`（fork 分支）。
- **禁止在 implementer 运行不到 30 分钟时主动 kill**
- **禁止在新起 implementer 时用 `checkout -B ... $DEFAULT_REF` 重置分支**（会丢弃 IMP 已做的工作）
- **禁止在派发 implementer 前研究任务** — 不要读代码、不要看页面、不要分析架构。这些是 implementer 的工作。违反此条会导致 implementer 拿到被 task-runner "污染"过的上下文，而不是原始任务描述

## 每轮执行流程

### Step 0: 确认身份 + 判断上下文

Agent 身份从 `loop-config.yaml` 的 `agent.name` 读取：

```bash
# 从 loop-config.yaml 读取 agent name + 加载项目变量
whoami=$(python -c "import yaml; print(yaml.safe_load(open('.loop-engineering/loop-config.yaml', encoding='utf-8'))['agent']['name'])")
eval $(python .claude/scripts/project_vars.py)

# 判断启动位置
if echo "$(pwd)" | grep -q "$AGENT_WS_LAST"; then
  echo "MODE=AGENT"
else
  echo "MODE=MAIN"
fi
```

| 输出 | 模式 | 处理方式 |
|------|------|----------|
| `MODE=AGENT` | **Agent 模式**（最常见） | 已在 agent worktree，直接同步+执行。**禁止 `git checkout master`** |
| `MODE=MAIN` | **主工程模式** | 需要 EnterWorktree 进入 agent worktree |

---

**0b. 检查 phase 文件**（跨 cron 周期的任务状态）：

phase 文件 `.loop-engineering/task-phase` 记录当前进行中任务的阶段、子代理 ID 和轮次。格式：`STAGE:AGENT_ID:BRANCH:ROUND`（ROUND 从 1 开始，每次 VFY FAIL 后 IMP 重试时递增）。

```bash
PHASE_FILE=".loop-engineering/task-phase"

if [ -f "$PHASE_FILE" ]; then
  IFS=':' read -r STAGE AGENT_ID BRANCH ROUND <<< "$(cat $PHASE_FILE)"
  # 兼容旧格式（无 ROUND 字段）
  ROUND="${ROUND:-1}"
  echo "PHASE=$STAGE AGENT=$AGENT_ID BRANCH=$BRANCH ROUND=$ROUND"
else
  echo "NO_PHASE"
fi
```

| phase 文件 | 含义 | 处理 |
|-----------|------|------|
| 不存在 | 无进行中任务 | 进入模式专属的 BUSY/IDLE 检查 |
| `IMP:agent_id:branch:round` | 等待 IMP 完成 | 检查本轮的 notification 队列 |
| `VFY:agent_id:branch:round` | 等待 VFY 完成 | 检查本轮的 notification 队列 |

**phase 文件存在时的处理逻辑**（不区分 Agent/主工程模式）：

1. **收到匹配的 notification（status=completed）**：
   - `IMP` → 删 phase 文件 → 进入 **Step 4** 派发 VFY
   - `VFY` → 先检查 `.loop-engineering/vfy-output-r$ROUND.md` 是否存在：`test -f .loop-engineering/vfy-output-r$ROUND.md || { echo "vfy-output-r$ROUND.md 不存在，重试 VFY" && exit 1; }` → 存在则读文件判断 PASS/FAIL → 删 phase 文件 → PASS 进 Step 5，FAIL 进重试

2. **收到匹配的 notification（status=killed）**：
   - 重新派发同类型 agent（不删 phase 文件，更新 agent ID）：`echo "$STAGE:$NEW_AGENT_ID:$BRANCH:$ROUND" > .loop-engineering/task-phase`
   - prompt 与之前相同，不修改 tasks.md，不重置分支

3. **无匹配 notification**：
   - 真正的 BUSY — 写心跳，输出等待状态，结束当前轮次。**不做任何 git 操作。**

**无 phase 文件时**：继续下面模式专属的 BUSY/IDLE 检查。

> **注意**：phase 文件存在时不执行下面的 git 清理操作——保护进行中的工作。

---

### Agent 模式（已在 agent worktree）

**先检查是否有进行中的任务**（任务标记 `[~]` 但无 phase 文件时，以 tasks.md 为准）：

```bash
python -c "
import yaml, sys
with open('.loop-engineering/loop-config.yaml', encoding='utf-8') as f:
    whoami = yaml.safe_load(f)['agent']['name']
with open('$TASKS_PATH', encoding='utf-8') as f:
    for line in f:
        if line.startswith('- [~]') and f'(→ {whoami})' in line:
            print('BUSY'); sys.exit(0)
print('IDLE')
"
```

- `BUSY` → **跳过所有 git 操作**，直接进入 Step 1（task_pick 会返回 BUSY，task-runner 等待）
- `IDLE` → 安全清理：

```bash
git fetch origin --prune 2>/dev/null || true
git checkout --detach --force $DEFAULT_REF && git clean -fd
python .claude/scripts/task_cleanup.py $whoami --project-root $PROJECT_ROOT
```

然后直接进入 Step 1 选任务。子代理自动继承当前 worktree 上下文 + agent MCP。

**完成后**：保持当前状态即可，不需要 ExitWorktree。

---

### 主工程模式（在主 worktree 被调用）

**0b. 确认 agent worktree 存在**（由 `loop setup` 创建）：

```bash
ls $AGENT_DIR/.git 2>/dev/null || {
  echo "Agent worktree 不存在，请先运行: loop setup"
  exit 1
}
```

**0c. 进入 agent worktree**：

调用 `EnterWorktree(path="$AGENT_DIR")`。

此后会话切换到 agent worktree，`.mcp.json` → MCP $AGENT_PORT。子代理自动继承。

**0d. 同步 agent worktree**（先检查是否有进行中的任务）：

```bash
python -c "
import yaml, sys
with open('.loop-engineering/loop-config.yaml', encoding='utf-8') as f:
    whoami = yaml.safe_load(f)['agent']['name']
with open('$TASKS_PATH', encoding='utf-8') as f:
    for line in f:
        if line.startswith('- [~]') and f'(→ {whoami})' in line:
            print('BUSY'); sys.exit(0)
print('IDLE')
"
```

- `BUSY` → **跳过所有 git 操作**，直接进入 Step 1
- `IDLE` → 安全清理：

```bash
git fetch origin --prune
git checkout --detach --force $DEFAULT_REF && git clean -fd
```

**0e. 检查已合入的远程分支**：

```bash
python .claude/scripts/task_cleanup.py $whoami --project-root $PROJECT_ROOT
```

> **注意**：Step 6 完成后必须 `ExitWorktree(action="keep")` 回到主 worktree。

### Step 1: 选任务

**写心跳**（每轮必须执行，即使已知有 BUSY 任务也不能跳过）：

```bash
python -c "from loop_engineering.control import write_heartbeat; write_heartbeat('.')"
```

**检查控制信号**：

```bash
# 暂停检查
python -c "from loop_engineering.control import is_paused; exit(0 if is_paused('.') else 1)" && echo "PAUSED" && exit 0
# throttle 读取
throttle=$(python -c "from loop_engineering.control import get_throttle; print(get_throttle('.'))")
```

**选任务**：

```bash
python .claude/scripts/task_pick.py $whoami --project-root $PROJECT_ROOT
```
- 输出格式: `taskID=xxx branch=agent/<whoami>/xxx-<slug> desc=... openSpec=true|false reopen=true|false user_feedback=...`
- `user_feedback=` 是用户反馈（来自 tasks.md 的缩进行，由 task-merge 拒绝时写入）
- `openSpec=true` → 任务关联 `openspec/changes/$desc/`，implementer 按 OpenSpec apply 流程处理
- 无匹配则 `NONE` → `ExitWorktree(action="keep")` → 停止。


### Step 2: Fork 分支 + 标记进行中

```bash
# 用 task_pick 输出的完整分支名
BRANCH="<task_pick 输出的 branch= 字段>"
REOPEN="<task_pick 输出的 reopen= 字段>"

if [ "$REOPEN" = "true" ]; then
  # reopen: 在已有分支上继续修改
  git fetch origin --prune 2>/dev/null || true
  git checkout $BRANCH
else
  # 新任务: 从最新 $DEFAULT_REF 创建分支（覆盖已存在的同名分支）
  git checkout -B $BRANCH $DEFAULT_REF
fi

# 主工程 tasks.md 标记进行中（不提交，只给人看）
# [ ] M6 (→ withg)  改为  [~] M6 (→ withg)
# [r] M6 (→ withg)  改为  [~] M6 (→ withg)
```

## 子代理提示词

IMP/VFY 提示词由 `build_prompt.py` 脚本拼装，task-runner 调用脚本获取完整提示词文本，直接传给 `Agent` 工具。

脚本参数：

| 参数 | 说明 |
|------|------|
| `imp \| vfy` | 子代理类型 |
| `--desc` | 任务描述（task_pick 输出的 `desc=`） |
| `--task-id` | 任务 ID（task_pick 输出的 `taskID=`） |
| `--branch` | 分支名（task_pick 输出的 `branch=`） |
| `--round` | 当前轮次（默认 1） |
| `--user-feedback` | 用户反馈（task_pick 输出的 `user_feedback=`） |
| `--open-spec` | OpenSpec 任务（task_pick 输出的 `openSpec=true` 时传此 flag） |
| `--reopen` | 重开任务（task_pick 输出的 `reopen=true` 时传此 flag，仅 imp） |

### Step 3: 派发实现子代理

用 `Agent` 工具，`run_in_background: true`。**禁止传 `isolation: "worktree"`**（会导致输出文件写入隔离工作树、task-runner 读取不到）。子代理**不会自动继承** worktree CWD — 必须在 prompt 中显式 cd 到 `$AGENT_DIR`。

```bash
# 构造 IMP 提示词
IMP_PROMPT=$(python .claude/scripts/build_prompt.py imp \
  --desc "$DESC" --task-id "$TASK_ID" --branch "$BRANCH" \
  --round "$ROUND" --user-feedback "$USER_FEEDBACK" \
  $([ "$OPEN_SPEC" = "true" ] && echo "--open-spec") \
  $([ "$REOPEN" = "true" ] && echo "--reopen"))
```

将 `$IMP_PROMPT` 作为 prompt 传给 Agent 工具。

### Step 3a: 记录 phase 文件

IMP spawn 完成后，写 phase 文件用于跨 cron 周期状态跟踪：

```bash
echo "IMP:<IMP_AGENT_ID>:$BRANCH:$ROUND" > .loop-engineering/task-phase
```

> `<IMP_AGENT_ID>` 从 Agent 工具返回的 agentId 获取。`ROUND` 从 Step 1 初始化为 1，每次 VFY FAIL 后递增。

### Step 3b: 等待 Implementer 完成

Implementer 完成后系统自动推送 `task-notification`。task-runner **不轮询文件**——同一会话内收到通知时立即处理；若会话已退出，则由下一轮 cron 触发 Step 0b 检测 phase 文件 + notification 到达后自动进入 Step 4。

**允许主动 kill 的条件**（必须同时满足以下三项）：
1. IMP 已运行 **> 30 分钟**
2. 检查 `.loop-engineering/imp-output-r$ROUND.md` 是否持续为空或未更新（连续两次 `stat` 相同且无新内容）
3. 分支上 **无新 commit**：`git log <BRANCH> --not $DEFAULT_REF --oneline` 为空

**不满足任一条件 → 不 kill，等下一轮 cron。**

kill 后直接重新派发 implementer：更新 phase 文件中 agent ID，prompt 相同，不修改 tasks.md，不重置分支。

### Step 4: 派发验证子代理

用 `Agent` 工具，`run_in_background: true`。**禁止传 `isolation: "worktree"`**。

```bash
# 构造 VFY 提示词
VFY_PROMPT=$(python .claude/scripts/build_prompt.py vfy \
  --desc "$DESC" --task-id "$TASK_ID" --branch "$BRANCH" \
  --round "$ROUND" --user-feedback "$USER_FEEDBACK" \
  $([ "$OPEN_SPEC" = "true" ] && echo "--open-spec"))
```

将 `$VFY_PROMPT` 作为 prompt 传给 Agent 工具。

### Step 4a: 更新 phase 文件

VFY spawn 完成后，更新 phase 文件：

```bash
echo "VFY:<VFY_AGENT_ID>:$BRANCH:$ROUND" > .loop-engineering/task-phase
```

### Step 4b: 等待 Verifier 完成

Verifier 完成后系统自动推送 `task-notification`。不轮询文件——同一会话内收到通知时立即处理；若会话已退出，则由下一轮 cron 触发 Step 0b 检测 phase 文件 + notification 到达后自动处理。

**Notification 到达时的处理**（在 Step 0b 中执行）：

VFY notification 到达时文件一定完整。读 `.loop-engineering/vfy-output-r$ROUND.md` 判断结论：

```bash
python -c "
with open('.loop-engineering/vfy-output-r$ROUND.md', encoding='utf-8') as f:
    for line in f:
        if '**PASS**' in line:
            print('PASS'); break
        elif '**FAIL**' in line:
            print('FAIL'); break
    else:
        print('UNKNOWN')
"
```

- **PASS** → 进入 Step 5
- **FAIL** → task-runner 进入 FAIL 重试流程：
  1. 递增 ROUND（`ROUND=$((ROUND + 1))`）
  2. SendMessage 当前 implementer，告知 VFY FAIL（IMP 自行读 `.loop-engineering/vfy-output-r*.md` 获取详情）
  3. implementer 修复，输出写入 `imp-output-r$ROUND.md`
  4. 重新派发 verifier（VFY 自行读取历史 `vfy-output-r*.md`）
- **UNKNOWN** → 视为 FAIL

**Verifier 被系统 kill**: 重新派发 verifier：更新 phase 文件中 agent ID，prompt 相同。不修改 tasks.md。

### Step 5: 结果处理

**PASS**:
1. 运行 `task_done.py`（内部完成 git add/commit/push + diff + tasks.md + 通知）：
   ```bash
   python .claude/scripts/task_done.py $whoami [taskID] [ROUND] [ROUND] \
     --project-root $PROJECT_ROOT \
     --output-dir $AGENT_DIR \
     --task-desc "<task_pick 输出的 desc= 字段>" \
     --do-commit
   ```
2. 清理 phase 文件 + working tree：
   ```bash
   rm -f .loop-engineering/task-phase
   git checkout --detach --force $DEFAULT_REF && git clean -fd
   ```

> **说明**：`task_done.py --do-commit` 会收集所有 `imp-output-r*.md` 和 `vfy-output-r*.md`，按交替格式（R1: IMP→VFY, R2: IMP→VFY, …）组装 commit message。只有最后一轮保留完整报告，前轮 IMP 精简为"反馈 + 修复内容"。然后 git add/commit/push，生成 diff、更新 tasks.md、弹通知。task-runner 不读报告内容。

**FAIL**（Verifier 发现测试失败）:
```
记录 FAIL 数 → SendMessage 当前 implementer（≤5次，每次携带 FAIL 测试点）
    ├─ FAIL 数收敛（↓）→ 继续
    └─ 5 次不收敛 → 新起 implementer（新鲜上下文，携带全部 FAIL 历史）
                        ├─ 最多 3 个 implementer
                        │   ├─ 收敛 → 继续
                        │   └─ 不收敛 → 下一个
                        └─ 3 个都不收敛 → 交给人
```

**Implementer 中断**（被系统 kill / 满足条件主动 kill）:
直接重新派发 implementer，prompt 与之前相同。**不修改 tasks.md**，**不重置分支**（不用 `checkout -B`）。新 implementer 自然继承当前 worktree 和分支状态，能看到上一轮 IMP 的 partial commit 或未提交改动。

**交人时**:
- tasks.md 行尾记录 `IMPx(未收敛)`
- 弹通知：
  ```bash
  python .claude/scripts/notify.py "[任务ID] 需人工介入" "FAIL 数不收敛 IMP1-3"
  ```
- 清理本地分支和 phase 文件 → `rm -f .loop-engineering/task-phase && git checkout --detach --force $DEFAULT_REF && git clean -fd && git branch -D <BRANCH>`

### Step 6: 收尾

| 模式 | 收尾操作 |
|------|----------|
| **Agent 模式** | agent worktree 已在上一步清理（reset + clean），保持在 detached HEAD，下次复用 |
| **主工程模式** | `ExitWorktree(action="keep")` 回到主 worktree |

等待人审查合入。合入后下轮 Step 0 的 `task_cleanup.py` 自动删远程分支。

## 交给人

FAIL 数不收敛（3 个 implementer 都不收敛）/ 架构变更 / 需改配表 / 任务不清 / >5 文件跨模块

## 输出

任务完成后输出等待合入摘要。完整报告（实现思路、实现过程、变更概要、向后兼容性、验证方案、验证结果、已知局限）已写入 commit message，可通过 `git log` 查看。

```markdown
## [任务ID] 等待合入
**分支**: <BRANCH> | **编译**: pass | **运行时**: pass
**审查**: git fetch && git diff $DEFAULT_REF...origin/<BRANCH>
```