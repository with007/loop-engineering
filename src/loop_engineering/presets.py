"""Loop Engineering 项目类型预设."""

PRESETS = {
    "unity-tolua": {
        "name": "Unity + ToLua",
        "description": "Unity 项目，使用 ToLua 热更新框架",
    },
    "python-server": {
        "name": "Python Server",
        "description": "Python Web/服务端项目",
    },
    "generic": {
        "name": "Generic",
        "description": "通用项目",
    },
}


def get_preset(name):
    """获取预设."""
    return PRESETS.get(name)


def list_presets():
    """列出所有预设."""
    return [(k, v["name"], v["description"]) for k, v in PRESETS.items()]


def apply_preset(config, preset_name):
    """应用预设类型到配置."""
    preset = get_preset(preset_name)
    if not preset:
        return config
    config["type"] = preset_name
    return config
