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
        }
    },
    "unity-basic": {
        "name": "Unity Basic",
        "description": "Unity 项目，纯 C#（无 Lua 热更新）",
        "verify": {
            "steps": [
                {"id": "compile", "type": "unity_refresh", "timeout": 120},
            ]
        }
    },
    "node-frontend": {
        "name": "Node.js Frontend",
        "description": "Node.js 前端项目",
        "verify": {
            "steps": [
                {"id": "build", "type": "npm_build"},
                {"id": "test", "type": "npm_test"},
            ]
        }
    },
    "go-backend": {
        "name": "Go Backend",
        "description": "Go 后端服务",
        "verify": {
            "steps": [
                {"id": "build", "type": "go_build"},
                {"id": "test", "type": "go_test"},
            ]
        }
    },
    "generic": {
        "name": "Generic",
        "description": "通用项目（仅 shell build + test）",
        "verify": {
            "steps": [
                {"id": "build", "type": "shell", "command": "npm run build || echo skipped"},
                {"id": "test", "type": "shell", "command": "npm test || echo skipped"},
            ]
        }
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
