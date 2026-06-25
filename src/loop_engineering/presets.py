"""Loop Engineering 项目类型预设."""

PRESETS = {
    "unity-tolua": {
        "name": "Unity + ToLua",
        "description": "Unity 项目，使用 ToLua 热更新框架",
        "verify": {
            "steps": [
                {"id": "compile", "type": "unity_refresh", "timeout": 120},
                {"id": "gen_lua_path", "type": "shell",
                 "command": "python scripts/genLuaPath.py",
                 "condition": "lua_files_added"},
                {"id": "runtime_test", "type": "lua_test", "timeout": 30},
            ]
        },
        "test": {
            "serve": "在 Unity Editor 中打开项目，进入 Play Mode",
            "scenarios": [
                {
                    "name": "编译检查",
                    "steps": [
                        "在 Unity Hub 中打开项目",
                        "等待编译完成",
                        "检查 Console 窗口：0 errors"
                    ],
                    "expected": "Console 无编译错误",
                },
                {
                    "name": "Play Mode 冒烟测试",
                    "steps": [
                        "进入 Play Mode",
                        "走一遍主要 UI 流程",
                        "检查 Console 无 Lua 异常"
                    ],
                    "expected": "游戏正常运行，无 Lua 异常",
                },
            ]
        },
    },
    "python-server": {
        "name": "Python Server",
        "description": "Python Web/服务端项目",
        "verify": {
            "steps": [
                {"id": "test", "type": "shell",
                 "command": "python -m pytest || echo skipped"},
            ]
        },
        "test": {
            "serve": "python -m <模块名>",
            "scenarios": [
                {
                    "name": "测试检查",
                    "steps": [
                        "运行 `python -m pytest`",
                        "确认所有测试通过"
                    ],
                    "expected": "全部测试通过，无失败",
                },
                {
                    "name": "服务启动冒烟测试",
                    "steps": [
                        "运行 serve 命令启动服务",
                        "在浏览器打开对应 URL",
                        "确认页面正常加载"
                    ],
                    "expected": "服务正常启动，页面可访问",
                },
            ]
        },
    },
    "generic": {
        "name": "Generic",
        "description": "通用项目",
        "verify": {
            "steps": [
                {"id": "build", "type": "shell", "command": "npm run build || echo skipped"},
                {"id": "test", "type": "shell", "command": "npm test || echo skipped"},
            ]
        },
        "test": {
            "serve": "npm run dev || npm start",
            "scenarios": [
                {
                    "name": "构建检查",
                    "steps": [
                        "运行项目的构建命令",
                        "确认无构建错误"
                    ],
                    "expected": "构建成功，无错误",
                },
            ]
        },
    },
}


def get_preset(name):
    """获取预设."""
    return PRESETS.get(name)


def list_presets():
    """列出所有预设."""
    return [(k, v["name"], v["description"]) for k, v in PRESETS.items()]


def apply_preset(config, preset_name):
    """将预设的 verify steps 应用到配置."""
    preset = get_preset(preset_name)
    if not preset:
        return config
    if "verify" not in config:
        config["verify"] = {}
    config["verify"]["steps"] = preset["verify"]["steps"]
    config["type"] = preset_name
    return config


def get_verify_template_vars(preset_name):
    """返回 VERIFY.md 和 TEST.md Jinja2 模板渲染所需的变量."""
    preset = get_preset(preset_name)
    if not preset:
        preset = get_preset("generic")
    return {
        "preset_name": preset_name,
        "preset_display_name": preset["name"],
        "preset_description": preset["description"],
        "test_serve": preset.get("test", {}).get("serve", ""),
        "test_url": preset.get("test", {}).get("url", ""),
        "test_scenarios": preset.get("test", {}).get("scenarios", []),
    }
