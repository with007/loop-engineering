---
name: verifier-unity
description: >
  Unity Editor verification. Covers C# compile checks, Lua runtime tests, config
  table parsing, proto compilation, and Lua path generation. Different change
  types need different verification primitives — this skill describes them so
  loop-verify can design a targeted plan from the diff.
---

# verifier-unity

验证 Unity Editor 变更。Unity Editor 必须已启动——verifier 已有 MCP 工具访问权限。

## 启动检查

确认 Unity MCP 可访问：
1. 调用 C# 编译工具 — 有响应即可
2. 调用控制台读取工具 — 确认 0 errors

Unity MCP 无响应 → **BLOCKED**。

```bash
<填写其他启动检查命令>
```

## 使用方法

1. 读 diff — 哪些文件变了，变了什么
2. 根据下方验证原语的适用条件，选择匹配的
3. 设计针对性验证方案 — 不跑无关步骤
4. 合并共享步骤：`refresh_unity` 只跑一次，`Launch Game` 只跑一次
5. 没有匹配的 → 跑 **默认** 流程

### 默认

```
refresh_unity → read_console → 确认 0 errors
<填写：是否需要 Launch Game + wait + read_console 作为兜底>
```

## 可用工具

**MCP 工具**（按功能匹配，不依赖具体命名）:
- 触发 C# 编译
- 读取控制台输出
- 在 Editor 中执行 C# 代码
- 启动/停止 Play Mode
- 注册/执行 Lua 测试

**项目脚本**:
| 脚本 | 用途 |
|------|------|
| `py -3 scripts/parseData.py -d` | 解析主配置表 txlsx → `_config/*.lua` |
| `py -3 scripts/parseData.py -c` | 解析主配置表（CN 版） |
| `py -3 scripts/genLuaPath.py` | 新增 Lua 文件后刷新 LuaPath.lua |
| `py -3 scripts/genPrefabDefine.py` | 新增 Prefab 后刷新 PrefabDefine.lua |
| `cmd /c ../<项目>Data/proto/buildproto.bat` | 编译 proto 文件 |
| <填写：其它 shell 脚本> | <填写用途> |

## 验证原语

不要按清单逐条执行。读 diff，理解变更，选择适用的原语，合并共享步骤。

### 编译检查

`refresh_unity` → `read_console` → 确认 0 errors

适用：`.cs` 文件变更、proto 变更（编译产物影响 C# 编译）

**CustomSettings.cs**（若项目使用 ToLua）：
`_GT(typeof(X))` 注册变更 → 确认 `Lua/Generate All` 已执行
→ 确认新类型不在 `staticClassTypes` 中（仅 Unity sealed class）

### 启动游戏 + 运行时检查

`Launch Game` → wait <填写等待秒数>s → `read_console` → 确认无 Lua Exception

适用：非注释的 `.lua` 变更、网络/战斗/UI 逻辑变更
若涉及 UI：确认对应面板可正常打开/关闭

**注意**：一次 Launch Game 覆盖所有需要运行时验证的变更。

### Lua 自动测试

若项目有 Lua 自动测试框架，调用 `/runtime-test` skill——它负责配置开关、
启动 Play Mode、轮询结果、报告、停止。

### 配置表变更

```bash
py -3 scripts/parseData.py -d
```
确认 exit code 0。若变更影响运行时：
```
Launch Game → wait 5s → read_console → 确认配置加载无异常
```

### Proto 变更

```bash
cmd /c ../<项目>Data/proto/buildproto.bat
```
确认 exit code 0。
```
refresh_unity → read_console → 确认 0 errors
```

### 新增 Prefab

```bash
py -3 scripts/genPrefabDefine.py
```
确认 exit code 0，PrefabDefine.lua 中包含新 Prefab 路径。

### 新增 Lua 文件

```bash
py -3 scripts/genLuaPath.py
```
确认 exit code 0，LuaPath.lua 中包含新文件路径。
```
Launch Game → wait 5s → read_console → 确认 requireLua 可正常加载
```

### <填写项目特有的验证原语>

<填写原语描述>

```bash
<填写验证命令>
```

适用：<填写适用条件>

## 探测

- 故意制造 C# 编译错误 → 控制台必须报出来
- 损坏的配置表 → 解析脚本应报错，不能崩溃
- Proto 语法错误 → 编译脚本应报清晰错误
- 缺失的 Lua 文件 → genLuaPath 应提示哪个文件找不到
- <填写项目特有的探测>

## 清理

Unity Editor 保持运行，不需要清理。Play Mode 由 `/runtime-test` skill 关闭。

```bash
<填写其他清理命令>
```

## 自更新

MCP 工具名变了 → 更新上方功能描述。
项目新增变更类型 → 补充对应原语。
构建脚本路径变了 → 更新命令。
- <填写其他自更新规则>
