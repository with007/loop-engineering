"""验证文档 API — VERIFY.md / TEST.md 读取和编辑."""

import os
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

router = APIRouter()


def _verify_dir(project_root):
    return project_root


def _template_dir(preset_type):
    """获取模板目录路径."""
    import loop_engineering
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(loop_engineering.__file__)))
    return os.path.join(os.path.dirname(pkg_dir), "templates", "verify", preset_type)


@router.get("/preview")
async def preview_template(request: Request, type: str = Query(...), doc: str = Query(...)):
    """返回模板文件原始 markdown 内容（setup 页面预览用）.

    Args:
        type: preset 名称（如 python-server, unity-tolua, generic）
        doc: verify 或 test
    """
    if doc not in ("verify", "test"):
        return JSONResponse({"error": "doc 必须是 verify 或 test"}, status_code=400)

    tmpl_dir = _template_dir(type)
    if not os.path.isdir(tmpl_dir):
        # fallback to generic
        tmpl_dir = _template_dir("generic")

    # 查找模板文件: VERIFY.md.j2 或 TEST.md.j2
    filename = "VERIFY.md.j2" if doc == "verify" else "TEST.md.j2"
    filepath = os.path.join(tmpl_dir, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": f"模板不存在: {filename}（preset: {type}）"}, status_code=404)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"content": content, "type": type, "doc": doc}


@router.get("/{doc}")
async def get_doc(request: Request, doc: str, project: str = Query(None)):
    """读取已部署的 VERIFY.md 或 TEST.md.

    Args:
        doc: verify 或 test
        project: 项目根目录（query param）
    """
    if doc not in ("verify", "test"):
        return JSONResponse({"error": "doc 必须是 verify 或 test"}, status_code=400)

    pr = _get_project_root(request, project)
    filename = "VERIFY.md" if doc == "verify" else "TEST.md"
    filepath = os.path.join(_verify_dir(pr), filename)

    if not os.path.exists(filepath):
        return JSONResponse({"content": "", "exists": False})

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"content": content, "exists": True}


@router.put("/{doc}")
async def save_doc(request: Request, doc: str, project: str = Query(None)):
    """保存编辑后的 VERIFY.md 或 TEST.md.

    Args:
        doc: verify 或 test
        project: 项目根目录（query param）
    """
    if doc not in ("verify", "test"):
        return JSONResponse({"error": "doc 必须是 verify 或 test"}, status_code=400)

    pr = _get_project_root(request, project)

    body = await request.json()
    content = body.get("content", "")

    target_dir = _verify_dir(pr)
    os.makedirs(target_dir, exist_ok=True)

    filename = "VERIFY.md" if doc == "verify" else "TEST.md"
    filepath = os.path.join(target_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return {"ok": True, "path": filepath}


def _get_project_root(request, project_q):
    """从 query param 或 request 或 env 获取项目根目录."""
    if project_q:
        return project_q
    if request:
        q = request.query_params.get("project")
        if q:
            return q
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())
