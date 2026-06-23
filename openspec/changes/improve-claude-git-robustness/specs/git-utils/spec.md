## git-utils

统一的 Git 操作工具模块，提供带重试的 fetch、离线检测、分支名安全转换。

### Requirements

#### GIT-001: fetch_with_retry

`fetch_with_retry(repo_path, remote="origin", retries=3)` 函数：
- 执行 `git fetch <remote>` 命令
- 失败时指数退避重试：第 1 次重试等 1s，第 2 次等 2s，第 3 次等 4s
- 所有重试耗尽后抛出 `RuntimeError`，包含最后一次错误信息
- 成功时返回 `True`
- 日志记录每次重试的 attempt 数和错误原因

#### GIT-002: 离线检测

`is_fetch_available(repo_path, remote="origin")` 函数：
- 尝试 `git fetch <remote>` 并立即返回布尔值
- 不抛异常，只返回 True/False
- 用于调用方在 fetch 前做决策（在线模式 vs 离线模式）

#### GIT-003: 分支名安全转换

`branch_to_dirname(branch)` 函数：
- 将分支名中的路径分隔符和非法字符（`/` `\` `:` `*` `?` `"` `<` `>` `|`）替换为 `__`
- 纯函数，不依赖文件系统

### Acceptance

- [ ] `fetch_with_retry` 网络正常时一次成功
- [ ] `fetch_with_retry` 网络异常时重试 3 次后抛异常
- [ ] `is_fetch_available` 不抛异常
- [ ] `branch_to_dirname("feature/foo-bar")` → `"feature__foo-bar"`
