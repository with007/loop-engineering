"""Server shared dependencies — extracted from app.py."""

from fastapi import Request
from fastapi.templating import Jinja2Templates
import os

_tpl_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_tpl_dir)
templates.env.cache = None


def is_htmx(request: Request):
    """Check if request is an HTMX request."""
    return request.headers.get("HX-Request", "") == "true"


def render_page(request: Request, template_name: str, context: dict):
    """Render a page template. HTMX requests get the partial; others get full base.html."""
    if is_htmx(request):
        resp = templates.TemplateResponse(request, template_name, context)
    else:
        content_html = templates.get_template(template_name).render(context)
        resp = templates.TemplateResponse(request, "base.html", {
            "request": request,
            "content": content_html,
        })
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def get_agent_name(pr):
    """Read agent name from loop-config.yaml."""
    from loop_engineering.config import read_config
    cfg = read_config(pr)
    return cfg.get("agent", {}).get("name", "")
