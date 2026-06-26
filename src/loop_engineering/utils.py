"""Loop Engineering 通用工具函数."""

import os
import tempfile


def atomic_write(path, content):
    """原子写入文件：先写临时文件，再 os.replace 到目标路径。

    写入过程中发生崩溃/中断时，目标文件不会出现部分内容。
    仅用于配置文件（YAML/JSON），心跳/暂停等信号文件继续使用 open().write()。

    Args:
        path: 目标文件路径
        content: 要写入的文本内容
    """
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise
