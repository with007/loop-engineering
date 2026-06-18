"""控制信号 API."""

import os
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


def _project_root():
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


class ThrottleRequest(BaseModel):
    interval: str  # e.g. "2m", "30s", "5m"


@router.get("/status")
def get_status():
    from loop_engineering.control import get_status as ctrl_status
    return ctrl_status(_project_root())


@router.post("/pause")
def pause():
    from loop_engineering.control import set_pause
    set_pause(_project_root(), True)
    return {"paused": True}


@router.delete("/pause")
def resume():
    from loop_engineering.control import set_pause
    set_pause(_project_root(), False)
    return {"paused": False}


@router.post("/next")
def next_cycle():
    from loop_engineering.control import _ensure_dir, _flag_path
    path = _flag_path(_project_root(), "next")
    _ensure_dir(_project_root())
    open(path, "w").close()
    return {"next": True}


@router.put("/throttle")
def set_throttle(req: ThrottleRequest):
    from loop_engineering.control import set_throttle as ctrl_set
    ctrl_set(_project_root(), req.interval)
    return {"throttle": req.interval}
