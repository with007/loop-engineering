---
name: verifier-cli
description: >
  CLI command verification. Tests CLI entry points, subcommands, flags, and
  error handling via direct invocation.
---

# verifier-cli

验证 CLI 命令变更。

## 启动检查

```bash
pip install -e .
```
```bash
loop --help
```
exit code 0 且输出含 "usage: loop" → 继续。不通 → **BLOCKED**。

## 使用方法

1. 读 diff — 哪个命令/子命令/参数变了
2. 匹配验证原语，不跑无关命令
3. 按依赖顺序执行（先 --help 确认存在，再带参数跑）
4. 没有匹配的 → 跑**默认**流程

```bash
# 默认：所有子命令 --help 确认可用
for cmd in setup init ui config teardown; do
  echo "=== loop $cmd --help ==="
  loop $cmd --help > /dev/null 2>&1 && echo "  OK" || echo "  FAIL"
done
```

## 可用工具

- Bash 命令 — 直接调用 CLI
- `Python -c` — 内联脚本校验输出

## 验证原语

### 入口可用性

```bash
loop --help
```
确认 exit code 0，列出可用子命令（setup / init / ui / config / teardown）。

适用：CLI 入口点变更、新增子命令

### 子命令验证

对 diff 涉及的子命令，跑 `--help` + 代表性参数：
```bash
loop <子命令> --help
```
确认 exit code 0，参数说明正确。

适用：子命令新增或参数变更

### 配置依赖命令

若命令依赖配置文件，确认能正常读取：
```bash
loop config show --project-root <project_root>
```
确认输出含项目名、agent 名、端口配置。

适用：config 模块变更、配置读写逻辑变更

### Setup 幂等性验证

`loop setup` 必须幂等——重复执行不报错、不破坏已有 worktree 和配置。

```bash
loop setup --project-root <project_root> -y
# 确认 exit code 0，输出含 "[OK]" 或 "跳过"（表示已存在）
# 再次执行
loop setup --project-root <project_root> -y
# 确认仍然 exit code 0，所有步骤显示"已是最新"或"已存在"
```

适用：setup.py 变更、worktree 创建/同步逻辑变更
注意：需要一个已有的 loop 项目来测试

### Teardown 验证

```bash
loop teardown --project-root <project_root> --dry-run
```
确认列出将要移除的 worktree 和注册表条目，不实际删除。

适用：teardown 逻辑变更

## 探测

- 未定义的 flag → 应报错并显示用法
  ```bash
  loop --nonexistent-flag 2>&1; echo "exit: $?"
  ```
- 缺失必填位置参数 → 应报错，不能静默执行
  ```bash
  loop setup 2>&1; echo "exit: $?"
  ```
- 不存在的输入文件路径 → 应报清晰错误
  ```bash
  loop setup --project-root /nonexistent/path 2>&1; echo "exit: $?"
  ```
- 无效 `KEY=VALUE` 格式 → 应指出哪里有问题
  ```bash
  loop config set "badformat" --project-root <project_root> 2>&1; echo "exit: $?"
  ```
- 不存在的子命令 → 应显示 usage 并报错
  ```bash
  loop nonexistent 2>&1; echo "exit: $?"
  ```

## 清理

CLI 无持久进程，不需要清理。

## 自更新

- 新增子命令 → 补充到原语中
- CLI 入口点变了 → 更新命令名
- setup/teardown 流程变了 → 更新对应原语
- 子命令参数变更 → 更新探测项和原语命令
