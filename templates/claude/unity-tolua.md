<!-- loop:rule:unity-open-start -->
## 打开 Unity 工程

在命令行启动 Unity Editor 打开当前工程：

```bash
# 基本打开（自动打开上次的场景）
"C:\Program Files\Unity 2021.3.6f1\Editor\Unity.exe" -projectPath "<工程根目录>"

# 打开指定场景
"C:\Program Files\Unity 2021.3.6f1\Editor\Unity.exe" -multiInstance -projectPath "<工程根目录>" -openScene "Assets/Scenes/Launcher.unity"
```

**参数说明**：

| 参数 | 说明 |
|------|------|
| `-projectPath <path>` | Unity 工程根目录（包含 `Assets/` 的目录） |
| `-multiInstance` | 允许多个 Unity Editor 实例同时运行 |
| `-openScene <path>` | 启动时打开指定场景（相对工程根目录的路径） |
| `-buildTarget <target>` | 切换平台（如 `Android`、`iOS`、`StandaloneWindows64`） |
| `-executeMethod <Method>` | 启动后执行指定静态方法（如 `MenuItems.Build`） |

> Unity Editor 路径随版本不同，常见位置：`C:\Program Files\Unity <version>\Editor\Unity.exe`。当前工程使用的 Unity 版本见 `ProjectSettings/ProjectVersion.txt`。
<!-- loop:rule:unity-open-end -->
