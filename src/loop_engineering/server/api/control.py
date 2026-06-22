"""控制信号 API."""

import os
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


def _project_root(project: str = None):
    if project:
        return project
    return os.environ.get("LOOP_PROJECT_ROOT", os.getcwd())


class ThrottleRequest(BaseModel):
    interval: str  # e.g. "2m", "30s", "5m"


@router.get("/status")
def get_status(project: str = Query(None)):
    from loop_engineering.control import get_status as ctrl_status
    return ctrl_status(_project_root(project))


@router.post("/pause")
def pause(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(_project_root(project), True)
    return {"paused": True}


@router.delete("/pause")
def resume(project: str = Query(None)):
    from loop_engineering.control import set_pause
    set_pause(_project_root(project), False)
    return {"paused": False}


@router.post("/next")
def next_cycle(project: str = Query(None)):
    from loop_engineering.control import _ensure_dir, _flag_path
    pr = _project_root(project)
    path = _flag_path(pr, "next")
    _ensure_dir(pr)
    open(path, "w").close()
    return {"next": True}


@router.put("/throttle")
def set_throttle(req: ThrottleRequest, project: str = Query(None)):
    from loop_engineering.control import set_throttle as ctrl_set
    ctrl_set(_project_root(project), req.interval)
    return {"throttle": req.interval}


@router.post("/start")
def start(project: str = Query(None)):
    from loop_engineering.control import start_loop
    return start_loop(_project_root(project))


@router.post("/stop")
def stop(project: str = Query(None)):
    from loop_engineering.control import stop_loop
    return stop_loop(_project_root(project))
