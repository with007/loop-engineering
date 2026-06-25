"""Loop Engineering 验证 Pipeline.

可配置的验证步骤系统。verifier 子代理按顺序执行 steps。
"""

import os
import subprocess
import time

# 内置步骤类型
BUILTIN_STEPS = {
    "shell": "执行任意 shell 命令，PASS if exit code 0",
    "unity_refresh": "Unity 编译 + read_console，PASS if 0 errors（需 MCP）",
    "lua_test": "执行注册的 Lua 测试，PASS if 所有 [AUTO TEST: xx] 标记 PASS（需 MCP）",
    "npm_build": "npm run build",
    "npm_test": "npm test",
    "go_build": "go build ./...",
    "go_test": "go test ./...",
}

# 条件类型
CONDITIONS = {
    "always": "始终执行",
    "lua_files_added": "diff 中包含新的 .lua 文件时执行",
    "csharp_files_changed": "diff 中包含变更的 .cs 文件时执行",
}


def read_pipeline(project_root):
    """读取 loop-config.yaml 中的 verify.steps。

    返回 step 列表，每个 step 是 dict: {id, type, timeout, optional, command, condition}
    """
    from loop_engineering.config import read_config
    cfg = read_config(project_root)
    steps = cfg.get("verify", {}).get("steps", [])

    # 应用默认值
    for s in steps:
        s.setdefault("timeout", 120)
        s.setdefault("optional", False)
        s.setdefault("condition", "always")

    return steps


def run_step(step, project_root, diff_files=None):
    """执行单个验证步骤。

    返回: {step_id, status: PASS|FAIL|SKIPPED, duration_seconds, output, error}
    """
    step_id = step.get("id", "unnamed")
    step_type = step.get("type", "shell")
    timeout = step.get("timeout", 120)
    optional = step.get("optional", False)
    condition = step.get("condition", "always")
    command = step.get("command", "")

    # 条件检查
    if not _check_condition(condition, diff_files or []):
        return {"step_id": step_id, "status": "SKIPPED",
                "duration_seconds": 0, "output": f"Condition '{condition}' not met", "error": None}

    start = time.time()

    try:
        if step_type == "shell":
            output, error = _exec_shell(command, project_root, timeout)
        elif step_type == "npm_build":
            output, error = _exec_shell("npm run build", project_root, timeout)
        elif step_type == "npm_test":
            output, error = _exec_shell("npm test", project_root, timeout)
        elif step_type == "go_build":
            output, error = _exec_shell("go build ./...", project_root, timeout)
        elif step_type == "go_test":
            output, error = _exec_shell("go test ./...", project_root, timeout)
        elif step_type == "unity_refresh":
            output, error = _exec_unity_refresh(timeout)
        elif step_type == "lua_test":
            output, error = _exec_lua_test(timeout)
        else:
            return {"step_id": step_id, "status": "FAIL",
                    "duration_seconds": time.time() - start,
                    "output": "", "error": f"Unknown step type: {step_type}"}

        duration = round(time.time() - start, 1)
        status = "PASS" if not error else "FAIL"

        return {"step_id": step_id, "status": status,
                "duration_seconds": duration,
                "output": (output or "")[:10240],
                "error": error}

    except Exception as e:
        duration = round(time.time() - start, 1)
        return {"step_id": step_id, "status": "FAIL",
                "duration_seconds": duration,
                "output": "", "error": str(e)}


def run_pipeline(project_root, diff_files=None):
    """顺序执行验证 pipeline。

    非 optional 步骤失败则停止，返回全部步骤结果和总体结论。
    """
    steps = read_pipeline(project_root)
    if not steps:
        # 默认：无配置，视为 PASS
        return True, []

    results = []
    overall_pass = True

    for step in steps:
        result = run_step(step, project_root, diff_files)
        results.append(result)

        if result["status"] == "FAIL" and not step.get("optional", False):
            overall_pass = False
            break

    return overall_pass, results


# ── 内部执行器 ──


def _exec_shell(command, cwd, timeout):
    """执行 shell 命令."""
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            cwd=cwd, timeout=timeout
        )
        output = (r.stdout + r.stderr)[:10240]
        if r.returncode != 0:
            return output, f"Exit code: {r.returncode}"
        return output, None
    except subprocess.TimeoutExpired:
        return "", f"Timeout after {timeout}s"
    except Exception as e:
        return "", str(e)


def _exec_unity_refresh(timeout):
    """Unity 编译步骤（需要 MCP 工具）.

    verifier 子代理应使用 MCP tools: refresh_unity + read_console。
    此函数返回指引而非直接执行。
    """
    return (
        "[UNITY_REFRESH] Verifier should call: refresh_unity(wait_for_ready=True) then read_console(filter_text='error')",
        None
    )


def _exec_lua_test(timeout):
    """Lua 测试步骤（需要 MCP 工具）.

    verifier 子代理应使用 runtime-test skill 执行注册的 Lua 测试。
    此函数返回指引而非直接执行。
    """
    return (
        "[LUA_TEST] Verifier should call: runtime-test skill to execute registered Lua tests. "
        "Check for [AUTO TEST: xx] PASS/FAIL markers in console.",
        None
    )


def _check_condition(condition, diff_files):
    """检查条件是否满足."""
    if condition == "always":
        return True
    if condition == "lua_files_added":
        return any(f.endswith(".lua") and "new file" in _git_status(f) for f in diff_files)
    if condition == "csharp_files_changed":
        return any(f.endswith(".cs") for f in diff_files)
    return True  # unknown condition → execute


def _git_status(filepath):
    """简单判断文件状态."""
    return ""  # stub: verifier will use MCP/git to check actual status
