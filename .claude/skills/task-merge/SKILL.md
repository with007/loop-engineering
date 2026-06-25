---
name: task-merge
description: >
  合入任务分支到 master。输入 task ID 或分支名，自动检查工作区状态，
  判断工作区改动与分支改动的关系，选择 stash 或 commit 路线完成合入。
  不指定分支时自动发现 agent 下未合入的分支供选择。
user_invocable: true
---

# Task Merge（任务分支合入）

你是合入助手。用户说"合入 xxx 分支"或"合入 task-xxx"，你来安全地把任务分支合入 master。

## 原则

- **不做 force push / force delete** — 只做安全的 merge
- **遇到冲突不自动解决** — 列出冲突文件，交给用户
- **不自动 push** — 只做本地合入，push 留给用户
- **stash 前告知用户判断依据** — 不静默 stash

## 流程

### Step 0: 无参数自动发现

如果用户只说"合入"而没有指定分支名或 task ID，自动查找 agent 下尚未合入 master 的分支：

```bash
git branch --no-merged master --list "agent/*"
```

- **0 个匹配** → 输出"没有未合入的 agent 分支"，退出
- **1 个匹配** → 直接用该分支，进入 Step 2
- **≥2 个匹配** → 列出所有匹配分支，让用户选一个

列出时显示每个分支的：
- 分支名
- 分支上的 commit 数（`git rev-list master..<branch> --count`）
- 最后一个 commit 的摘要（`git log master..<branch> --oneline -1`）

让用户选择（输入序号），选择后进入 Step 2。

### Step 1: 解析目标分支

**仅在用户提供了分支名或 task ID 时执行此步骤。**

根据用户输入判断：

**情况 A: 用户给了完整分支名**（如 `agent/with/a1b2c3d4-翻译tab`）

```bash
git branch -a | grep "<分支名>"
```
- 存在 → 直接用
- 不存在 → 报错退出

**情况 B: 用户给了 task ID**（如 `task-a35f86a5`）

```bash
git branch -a | grep "<taskID>"
```
- 0 个匹配 → 报错退出，"未找到包含 <taskID> 的分支"
- 1 个匹配 → 直接用
- ≥2 个匹配 → 列出所有匹配分支，让用户选一个

### Step 2: 显示分支概要

```bash
# 分支上有哪些 commit（不在 master 上的）
git log master..<branch> --oneline

# 改动了哪些文件
git diff master...<branch> --stat
```

输出清晰的分支摘要给用户看，然后确认是否继续合入。用户确认后进入 Step 3。

### Step 3: 检查工作区状态

```bash
git status --porcelain
```

- **空** → 工作区干净，跳到 Step 5（直接 merge）
- **非空** → 工作区有未提交改动，进入 Step 4

### Step 4: 分类工作区改动

对比工作区改动文件和分支改动文件的重叠程度：

```bash
# 分支改动的文件（相对于 master）
git diff master...<branch> --name-only

# 工作区改动的文件
git diff --name-only
# 以及 untracked 文件
git ls-files --others --exclude-standard
```

**判断逻辑**：

1. 计算重叠：两边都出现的文件数 / 分支改动文件数
2. **重叠 ≥ 50%** → 工作区改动很可能是分支改动的半成品 → **推荐 stash 路线**
3. **重叠 < 50%** → 工作区改动是独立工作 → **推荐 commit 路线**

告知用户判断依据（哪些文件重叠、哪些不重叠）和建议的路线。**一步确认**：让用户选择 stash 路线 / commit 路线 / 取消。

### Step 5: 执行合入

#### Stash 路线（工作区改动 = 同一件事的半成品）

重叠文件的改动会被分支的最终版本覆盖，只需保留不重叠的文件：

```bash
# 1. 只 stash 重叠的文件（不重叠的文件留在工作区不动）
git stash push -m "task-merge: auto stash before merging <branch>" -- <重叠文件列表>

# 2. 如果有 untracked 文件会被 merge 覆盖，先移走
# （git merge 遇到 untracked 且分支也有的文件会报错）

# 3. 合并分支
git merge <branch> --no-edit
```

如果 merge 冲突：
- 列出冲突文件
- 告诉用户：stash 里还有原始改动（`git stash list`），可以 `git stash pop` 恢复
- 停止

如果 merge 成功：
```bash
# 4. 清理 stash（重叠文件已被分支版本覆盖，不需要恢复）
git stash drop
```

#### Commit 路线（工作区改动 = 独立工作）

```bash
# 1. 提交工作区改动
git add -A
git commit -m "WIP: 合入 <branch> 前的本地改动"

# 2. 合并分支
git merge <branch> --no-edit
```

如果 merge 冲突：
- 列出冲突文件
- 告诉用户：工作区改动已保存在倒数第二个 commit，解决冲突后 `git merge --continue`
- 停止

### Step 6: 验证结果

```bash
git log --oneline -3
git status
```

输出摘要：
- 合入的 commit 信息
- 当前分支位置
- 工作区是否干净
- 如果用了 stash 路线，确认 stash 已清理

## 输出示例

### 干净合入

```
## 合入完成 ✅
**分支**: agent/with/a1b2c3d4-翻译tab
**方式**: 直接 merge（工作区干净）
**新增 commit**: ffac9d2 a1b2c3d4: 翻译tab页标题为中文
**当前状态**: master 已前进 2 个 commit，工作区干净
```

### Stash 路线

```
## 合入完成 ✅
**分支**: agent/with/a1b2c3d4-翻译tab
**方式**: stash → merge（工作区改动与分支改动高度重叠，判断为同一件事）
**新增 commit**: ffac9d2 task-a35f86a5: 修复页面自动刷新导致输入被清空
**当前状态**: master 已前进 2 个 commit，工作区干净
```

### Commit 路线

```
## 合入完成 ✅
**分支**: agent/with/a1b2c3d4-翻译tab
**方式**: commit 工作区 → merge（工作区改动与分支改动不重叠，判断为独立工作）
**工作区备份**: commit abc1234 "WIP: 合入 agent/with/a1b2c3d4-翻译tab 前的本地改动"
**新增 commit**: ffac9d2 task-a35f86a5: 修复页面自动刷新导致输入被清空
**当前状态**: master 已前进 2 个 commit，工作区干净
```

### 冲突

```
## 合入遇到冲突 ⚠️
**分支**: agent/with/a1b2c3d4-翻译tab
**冲突文件**:
  - src/loop_engineering/server/templates/tasks.html
  - src/loop_engineering/server/templates/runs.html
**stash 备份**: stash@{0}（可 git stash pop 恢复原始改动）
**下一步**: 手动解决冲突 → git add <冲突文件> → git merge --continue
```
