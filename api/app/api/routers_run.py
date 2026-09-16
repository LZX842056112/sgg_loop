from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Project
from app.db.session import get_session
from app.engine.runner import enqueue_run, get_run_package
from app.schemas.run import (
    AnalysisPackageRead, AnalysisRunRead, RunEnqueueRead, RunEventRead,
)
from app.services.run_events import list_run_events

router = APIRouter(prefix="/projects/{project_id}", tags=["runs"])


def _get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# ── 创建运行（后台模式）──
@router.post("/runs", response_model=RunEnqueueRead, status_code=status.HTTP_202_ACCEPTED)
def create_run(
        project_id: str,
        session: Session = Depends(get_session),
) -> dict:
    """创建分析运行并立即入队——后台 Worker 接管执行。"""
    project = _get_project_or_404(session, project_id)
    try:
        run, job = enqueue_run(session, project)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    session.refresh(run)
    session.refresh(job)
    return {"run": run, "job": job}


# ── 查询运行列表 ──

@router.get("/runs", response_model=list[AnalysisRunRead])
def list_runs(
        project_id: str,
        session: Session = Depends(get_session),
) -> list[AnalysisRun]:
    _get_project_or_404(session, project_id)
    statement = (
        select(AnalysisRun)
        .where(AnalysisRun.project_id == project_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    )
    return list(session.scalars(statement).all())


# ── 获取运行分析包 ──

@router.get("/runs/{run_id}", response_model=AnalysisPackageRead)
def get_run(
        project_id: str,
        run_id: str,
        session: Session = Depends(get_session),
) -> dict:
    _get_project_or_404(session, project_id)
    package = get_run_package(session, project_id, run_id)
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return package


# ── 获取运行事件 ──

@router.get("/runs/{run_id}/events", response_model=list[RunEventRead])
def get_run_events(
        project_id: str,
        run_id: str,
        session: Session = Depends(get_session),
) -> list:
    _get_project_or_404(session, project_id)
    run = session.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return list_run_events(session, project_id, run_id)
