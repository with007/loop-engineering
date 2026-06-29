# Loop Engineering — Claude Rules

## 1. Bug 修复流程

如果是报错/bug 而不是新需求，**不要直接开始修改代码**。流程：

1. 先读相关代码，定位问题根因
2. 告诉用户：发现了什么问题、是什么原因导致的
3. 说明打算怎么修复
4. 用户确认后再动手

这避免对 bug 理解偏差导致越修越远。

## 2. 修改后自测（必须用真实环境）

修改完代码之后，**必须用和生产环境一致的方式跑通测试**，禁止用简化替代品。

### 原则

测试要用**实际生产中的命令、进程、数据和流程**，而不是能跑通的简化版。

- 改了启动/停止/聚焦 loop 窗口的代码 → 必须启动真实 `claude --dangerously-skip-permissions` 进程来验证
- 改了 API 端点 → 调真实端点或直接调底层函数，验证返回值
- 改了模板 → 用真实模板文件渲染，检查关键字段
- 改了 setup/teardown → 找实际项目跑一遍完整流程

### 禁止

- 用 `echo` / `timeout` / `ping` 替代真实业务命令来"模拟"
- 用与生产不同的参数或环境来"方便测试"
- 只测 happy path 不测异常

## 3. 模板修改规则

修改 Skill / Command / Config 时，**始终改模板源，不要改部署副本**。

### 源与副本

| 角色 | 路径 | 说明 |
|------|------|------|
| **模板源** | `templates/skills/<name>/SKILL.md` 或 `.j2` | 唯一可编辑的源 |
| **部署副本** | `.claude/skills/<name>/SKILL.md` | `loop setup` 自动生成，会被覆盖 |

- `.j2` 模板通过 Jinja2 渲染生成 `.md`（变量从 `loop-config.yaml` 读取）
- 裸 `.md` 模板直接拷贝
- 两种情况下部署副本都是**生成产物**，手动改会在下次 `loop setup` 时丢失

### 检查方法

修改模板源后，渲染并对比确认一致性：

```bash
python -c "
from jinja2 import Environment, BaseLoader
vars = {...}  # 从 setup.py 的 j2_vars 复制
env = Environment(loader=BaseLoader())
with open('templates/skills/<name>/SKILL.md.j2') as f:
    rendered = env.from_string(f.read()).render(**vars)
with open('.claude/skills/<name>/SKILL.md') as f:
    deployed = f.read()
print('OK' if rendered == deployed else 'DIFF')
"
```

### 禁止

- 不要直接编辑 `.claude/skills/`、`.claude/commands/` 下的文件
- 不要同时保留 `.j2` 和闲置 `.md`（用 `.j2` 就删 `.md`）

## 4. TEST.md / VERIFY.md 定位

`TEST.md` 和 `VERIFY.md` 是**方法论参考**，不是必须全部执行的死清单。

- 文档自身已说明定位（"测试方法论参考"、"验证范围由变更驱动"）
- 使用方只需引用文档，按其中说明执行，不要重新解释文档定位
- 执行时：先理解变更范围，再从中选择涉及模块的手段，未涉及的跳过
