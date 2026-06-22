# unity-test — Unity 自动测试运行器

## 触发

用户说"跑测试 / 测试一下 / 自动测试 / 验证一下"时使用。适用于所有 Unity 自动测试场景（战斗 / UI / 网络 / 系统等）。

## 工作机制

每个测试由三个部件串联：

```
config.json flag  →  入口点 requireLua  →  测试脚本（输出 [AUTO TEST: 名] 标记）
```

- **config.json flag**：布尔开关，放在项目根 `config.json` 中，控制是否加载测试脚本。命名建议 `autoTest<场景>`（如 `autoTestBattle`）。
- **入口点 requireLua**：在合适的初始化位置（如 `MainGameRoot.Start()`）检查 flag，为 `true` 时 `requireLua("路径.测试脚本")`。
- **测试脚本**：用 `lc.delayFunc` 串联异步步骤，通过 `f_print` 输出标准标记，由 skill 轮询 console 识别。

## 测试标记约定

测试脚本中统一用以下格式输出，skill 据此判定开始/通过/失败/完成：

```lua
f_print("===== [AUTO TEST: 测试名] 开始 =====")   -- 测试启动
f_print("[AUTO TEST: 测试名] PASS: 说明")           -- 单步通过
f_print("[AUTO TEST: 测试名] FAIL: 原因")           -- 单步失败
f_print("===== [AUTO TEST: 测试名] 完成 =====")     -- 全链路完成
```

## 接入新测试

1. 写一个 Lua 测试脚本，遵循下方的"实现模式"和"标记约定"
2. 执行 `scripts/genLuaPath.py` 刷新 `LuaPath.lua`（新增文件必须，否则 `requireLua` 找不到）
3. 在 `config.json` 中添加对应 flag（如 `"autoTestBattle": true`）
4. 在入口点用 flag 包裹 `requireLua`：
   ```lua
   if C._config.autoTestBattle then requireLua("battle/MyTest") end
   ```
5. 在域 CLAUDE.md 中记录：测试名、config flag、预估耗时

## 运行流程

```
setup 检查 → 开启 flag → Play Mode → 轮询标记 → 报告 → 停止
```

### 详细步骤

1. **Setup 检查** —
   - `config.json` 中目标 flag 未开启 → 设为 `true`
   - 入口点缺少对应 `requireLua` → 补上
   - 有新 Lua 测试文件 → 执行 `scripts/genLuaPath.py`
   - 有 C# 修改未编译 → `refresh_unity` + `read_console` 确认 0 errors
2. **Play Mode** — `manage_editor play`
3. **轮询等待** —
   - 每 3s 用 `read_console`（不带 filter）检查一次
   - 直到所有测试输出 `[AUTO TEST: 名] 完成` 或 `FAIL`，判断结束
   - 超时未完成（根据测试规模估算）→ 报告"超时未完成"并停止
4. **读结果** —
   - 先 `read_console` 搜 `[AUTO TEST:` 标记
   - 若输出截断（>50 条），fallback 到 `grep -a "AUTO TEST" c:/Users/withg/AppData/Local/Unity/Editor/Editor.log`
5. **报告结果** —
   ```markdown
   ## 测试报告
   **PASS: N | FAIL: N | 总计: N**

   | 测试名 | 结果 | 说明 |
   |--------|------|------|
   | xxx    | PASS | ...  |
   | yyy    | FAIL | 原因 |
   ```
6. **停止** — `manage_editor stop`

### 注意事项

- **Lua 修改不需刷 Unity**，改完即生效；C# 修改需先 `refresh_unity` 等编译完
- 网络超时（Firebase SDK 等）卡住时，重试即可
- 如果测试在 Play Mode 里就报错了，console 能直接看到 Lua 异常

## 测试代码实现模式

### 基本结构

```lua
-- 由入口点在 config flag 开启时 requireLua
local function tryStart()
    if not <前置条件> then
        lc.delayFunc(0.5, tryStart)   -- 条件未满足，轮询重试
        return
    end
    f_print("===== [AUTO TEST: 名] 开始 =====")
    -- 触发游戏逻辑...
    lc.delayFunc(<延迟>, function()
        -- 下一步操作...
        lc.delayFunc(<延迟>, function()
            f_print("===== [AUTO TEST: 名] 完成 =====")
        end)
    end)
end
lc.delayFunc(0.5, tryStart)
```

### 核心模式

| 模式 | 说明 |
|------|------|
| **`lc.delayFunc` 链式串联** | 所有异步步骤通过 `lc.delayFunc(delay, callback)` 串联，避免协程复杂度 |
| **`tryStart` 前置轮询** | 用 `lc.delayFunc` 自循环等待前置条件（如场景就绪、管理器初始化），满足后才进入正式测试 |
| **`waitPanel` UI 轮询** | UI 异步弹出时，用 `lc.delayFunc` 轮询检查面板状态，设重试上限防止死循环 |
| **超时 FAIL** | 轮询超过 N 次仍未满足条件 → `f_print("[AUTO TEST: 名] FAIL: 原因")` 并 return |

### 典型场景：等待异步 UI 面板

```lua
local retry = 0
local function waitPanel()
    retry = retry + 1
    if <面板就绪条件> then
        f_print("[AUTO TEST: 名] PASS: 说明")
        -- 继续后续步骤...
    elseif retry < 30 then
        lc.delayFunc(0.2, waitPanel)   -- 每 0.2s 重试，最多 30 次（6s）
    else
        f_print("[AUTO TEST: 名] FAIL: 面板未就绪（超时）")
    end
end
lc.delayFunc(0.5, waitPanel)
```
