"""验证文档 API — 读取和编辑 verifier skills 和 TEST.md."""

import os
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from loop_engineering.path_utils import resolve_project_root

router = APIRouter()


def _skills_dir(project_root):
    """verifier skills 目录."""
    return os.path.join(project_root, ".claude", "skills")


@router.get("/skills")
async def list_skills(request: Request, project: str = Query(None)):
    """列出可用的 verifier skills."""
    pr = resolve_project_root(project=project, request=request)
    sd = _skills_dir(pr)

    skills = []
    if os.path.isdir(sd):
        for name in sorted(os.listdir(sd)):
            if not name.startswith("verifier-"):
                continue
            skill_md = os.path.join(sd, name, "SKILL.md")
            skills.append({
                "name": name,
                "label": name.replace("verifier-", ""),
                "exists": os.path.exists(skill_md),
            })

    return {"skills": skills}


@router.get("/preview")
async def preview_template(request: Request, type: str = Query(...), doc: str = Query("test")):
    """返回 TEST.md.j2 或 verifier skill 模板内容（setup 页面预览用）."""
    import loop_engineering
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(loop_engineering.__file__)))
    tmpl_dir = os.path.join(os.path.dirname(pkg_dir), "templates", "verify", type)
    if not os.path.isdir(tmpl_dir):
        tmpl_dir = os.path.join(os.path.dirname(pkg_dir), "templates", "verify", "generic")

    # verifier skill preview: /api/docs/preview?type=...&doc=verifier-web
    if doc.startswith("verifier-"):
        filepath = os.path.join(tmpl_dir, "skills", doc, "SKILL.md")
        if not os.path.exists(filepath):
            return JSONResponse({"error": f"模板不存在: {doc}"}, status_code=404)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "type": type, "doc": doc}

    filepath = os.path.join(tmpl_dir, "TEST.md.j2")
    if not os.path.exists(filepath):
        return JSONResponse({"error": f"模板不存在: TEST.md.j2"}, status_code=404)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"content": content, "type": type, "doc": "test"}


@router.get("/skills/preview")
async def preview_skills(request: Request, type: str = Query(...)):
    """列出某类型的 verifier skill 模板."""
    import loop_engineering
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(loop_engineering.__file__)))
    tmpl_dir = os.path.join(os.path.dirname(pkg_dir), "templates", "verify", type, "skills")

    skills = []
    if os.path.isdir(tmpl_dir):
        for name in sorted(os.listdir(tmpl_dir)):
            if os.path.isdir(os.path.join(tmpl_dir, name)):
                skills.append({"name": name, "label": name.replace("verifier-", "")})

    if not skills:
        # fallback to generic
        tmpl_dir = os.path.join(os.path.dirname(pkg_dir), "templates", "verify", "generic", "skills")
        if os.path.isdir(tmpl_dir):
            for name in sorted(os.listdir(tmpl_dir)):
                if os.path.isdir(os.path.join(tmpl_dir, name)):
                    skills.append({"name": name, "label": name.replace("verifier-", "")})

    return {"skills": skills}


@router.get("/{doc}")
async def get_doc(request: Request, doc: str, project: str = Query(None)):
    """读取 verifier skill 或 TEST.md.

    Args:
        doc: verifier skill 名 (如 verifier-web) 或 "test"
        project: 项目根目录（query param）
    """
    pr = resolve_project_root(project=project, request=request)

    if doc == "test":
        filepath = os.path.join(pr, "TEST.md")
    elif doc.startswith("verifier-"):
        filepath = os.path.join(_skills_dir(pr), doc, "SKILL.md")
    else:
        return JSONResponse({"error": "doc 必须是 verifier skill 名或 test"}, status_code=400)

    if not os.path.exists(filepath):
        return JSONResponse({"content": "", "exists": False})

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"content": content, "exists": True}


@router.put("/{doc}")
async def save_doc(request: Request, doc: str, project: str = Query(None)):
    """保存 verifier skill 或 TEST.md.

    Args:
        doc: verifier skill 名 (如 verifier-web) 或 "test"
        project: 项目根目录（query param）
    """
    pr = resolve_project_root(project=project, request=request)

    body = await request.json()
    content = body.get("content", "")

    if doc == "test":
        filepath = os.path.join(pr, "TEST.md")
    elif doc.startswith("verifier-"):
        filepath = os.path.join(_skills_dir(pr), doc, "SKILL.md")
    else:
        return JSONResponse({"error": "doc 必须是 verifier skill 名或 test"}, status_code=400)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return {"ok": True, "path": filepath}
