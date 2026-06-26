"""运行历史 API."""

import os
from fastapi import APIRouter, Query
from loop_engineering.path_utils import resolve_project_root

router = APIRouter()


@router.get("/list")
def list_runs(
    whoami: str = Query(None),
    result: str = Query(None),
    days: int = Query(None),
    limit: int = Query(50),
    project: str = Query(None),
):
    from loop_engineering.runlog import list_runs as query_runs
    entries = query_runs(resolve_project_root(project=project), whoami=whoami, result=result, days=days, limit=limit)
    return {"runs": entries, "count": len(entries)}


@router.get("/pass-rate")
def pass_rate(days: int = Query(7), project: str = Query(None)):
    from loop_engineering.runlog import get_pass_rate
    passed, total, rate = get_pass_rate(resolve_project_root(project=project), days=days)
    return {"passed": passed, "total": total, "rate": round(rate * 100, 1)}
