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


from fastapi.responses import StreamingResponse

from app.db.session import get_worker_session_factory
from app.services.run_events import (
    encode_many_sse, encode_sse, list_run_events, stream_run_events_live,
)


def _get_run_or_404(session: Session, project_id: str, run_id: str) -> AnalysisRun:
    run = session.get(AnalysisRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── SSE 端点 ──

@router.post("/runs/stream")
def create_run_stream(
        project_id: str,
        session: Session = Depends(get_session),
) -> StreamingResponse:
    """创建运行并返回 SSE 流——适合"立即执行"的场景。"""
    project = _get_project_or_404(session, project_id)
    try:
        run, _job = enqueue_run(session, project)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.expire_all()

    # 轮询已写入的事件并一次性推送
    events = list_run_events(session, project.id, run.id)
    return StreamingResponse(
        iter([encode_many_sse(events)]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/events/stream")
def stream_run_events_endpoint(
        project_id: str,
        run_id: str,
        after_sequence: int = 0,
) -> StreamingResponse:
    """实时 SSE 事件流——持续推送 Worker 写入的新事件。"""
    session_factory = get_worker_session_factory()
    with session_factory() as session:
        _get_run_or_404(session, project_id, run_id)

    return StreamingResponse(
        stream_run_events_live(
            session_factory,
            project_id=project_id,
            run_id=run_id,
            after_sequence=after_sequence,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


from app.services.run_jobs import cancel_run_jobs, create_run_job
from app.services.run_events import record_run_event


@router.post("/runs/{run_id}/cancel", response_model=AnalysisRunRead)
def cancel_run(
        project_id: str,
        run_id: str,
        session: Session = Depends(get_session),
) -> AnalysisRun:
    project = _get_project_or_404(session, project_id)
    run = _get_run_or_404(session, project_id, run_id)

    # 取消所有活跃 job
    cancel_run_jobs(session, run.id)

    # 更新 run 和 project 状态
    run.status = "cancelled"
    run.stop_reason = "User cancelled the run."
    project.status = "cancelled"

    record_run_event(
        session, project.id, run.id, "run_cancelled",
        {"status": "cancelled"},
    )
    session.commit()
    session.refresh(run)
    return run


@router.post("/runs/{run_id}/retry", response_model=RunEnqueueRead,
             status_code=status.HTTP_202_ACCEPTED)
def retry_run(
        project_id: str,
        run_id: str,
        session: Session = Depends(get_session),
) -> dict:
    project = _get_project_or_404(session, project_id)
    run = _get_run_or_404(session, project_id, run_id)

    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=409,
            detail="Only failed or cancelled runs can be retried",
        )

    run.status = "queued"
    run.stop_reason = None
    project.status = "queued"

    job = create_run_job(session, project.id, run.id, "retry")
    record_run_event(
        session, project.id, run.id, "run_retry_queued",
        {"job_id": job.id, "status": run.status},
    )
    session.commit()
    session.refresh(run)
    session.refresh(job)
    return {"run": run, "job": job}


from app.engine.runner import resume_run
from app.services.reports import build_analysis_package


@router.post("/runs/{run_id}/resume", response_model=AnalysisRunRead)
def resume_existing_run(
        project_id: str,
        run_id: str,
        session: Session = Depends(get_session),
) -> AnalysisRun:
    project = _get_project_or_404(session, project_id)
    run = _get_run_or_404(session, project_id, run_id)

    try:
        resume_run(session, project, run)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    session.commit()
    session.refresh(run)
    return build_analysis_package(session, run)  # 追加 import


from app.db.models import utc_now, Question
from app.schemas.run import QuestionAnswerCreate, QuestionRead
from app.services.audit import record_event


@router.post("/questions/{question_id}/answer", response_model=QuestionRead)
def answer_question(
        project_id: str,
        question_id: str,
        payload: QuestionAnswerCreate,
        session: Session = Depends(get_session),
) -> Question:
    project = _get_project_or_404(session, project_id)
    question = session.get(Question, question_id)
    if question is None or question.project_id != project.id:
        raise HTTPException(status_code=404, detail="Question not found")

    question.status = "answered"
    question.answer_text = payload.answer_text
    question.answered_at = utc_now()

    # 特殊处理：如果问题是关于 analysis_goal 的，同步更新项目
    if (
            question.metadata_json.get("missing_field") == "analysis_goal"
            and not project.analysis_goal
    ):
        project.analysis_goal = payload.answer_text

    record_event(
        session,
        event_type="question.answered",
        message="Loop question answered",
        project_id=project.id,
        payload={"question_id": question.id, "run_id": question.run_id},
    )
    session.commit()
    session.refresh(question)
    return question
