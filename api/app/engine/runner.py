from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun, EvidenceItem, Finding, LoopTurn, Project,
    QualityScore, Question, Recommendation, Risk, RunJob,
)
from app.db.session import bind_worker_session_to
from app.engine.state_machine import ensure_can_start_run
from app.services.audit import record_event
from app.services.run_events import record_run_event
from app.services.run_jobs import create_run_job


def initialize_run(session: Session, project: Project) -> AnalysisRun:
    """创建一次 Loop 运行——不立即执行，只做状态校验和初始化。"""
    ensure_can_start_run(project.status)
    run = AnalysisRun(
        project_id=project.id,
        status="running",
        max_turns=project.max_turns,
    )
    project.status = "running"
    session.add(run)
    session.flush()
    run.thread_id = f"run:{run.id}"
    record_event(
        session,
        event_type="run.started",
        message="Loop 运行已启动",
        project_id=project.id,
        payload={"run_id": run.id},
    )
    return run


def enqueue_run(
        session: Session,
        project: Project,
        job_type: str = "start",
        payload: dict | None = None,
) -> tuple[AnalysisRun, RunJob]:
    """创建后台运行任务——HTTP 只负责登记，实际执行由 Worker 接管。

    这是 durable runtime 的入口：浏览器断开不影响已排队的 run。
    """
    ensure_can_start_run(project.status)
    bind_worker_session_to(session)

    run = AnalysisRun(
        project_id=project.id,
        status="queued",
        max_turns=project.max_turns,
        execution_mode="background",
    )
    project.status = "queued"
    session.add(run)
    session.flush()
    run.thread_id = f"run:{run.id}"

    job = create_run_job(session, project.id, run.id, job_type, payload)
    record_run_event(
        session, project.id, run.id, "run_queued",
        {"status": run.status, "job_id": job.id},
    )
    return run, job


# ── 以下方法在 Module 18 补全 LangGraph 引擎后启用 ──
def append_turn(
        session: Session, run: AnalysisRun, project: Project,
        node_name: str, action: str, observation: str,
        metadata: dict | None = None,
) -> LoopTurn:
    """记录一次 Loop 轮次。"""
    turn = LoopTurn(
        run_id=run.id, project_id=project.id,
        turn_index=run.current_turn + 1,
        node_name=node_name, action=action,
        observation=observation, status="completed",
        metadata_json=metadata or {},
    )
    session.add(turn)
    session.flush()
    run.current_turn = turn.turn_index
    return turn


def get_run_package(session: Session, project_id: str, run_id: str) -> dict:
    """组装一次运行的完整分析包——所有产出物。"""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        return None

    return {
        "run": run,
        "turns": list(
            session.scalars(
                select(LoopTurn)
                .where(LoopTurn.run_id == run_id)
                .order_by(LoopTurn.turn_index.asc(), LoopTurn.id.asc())
            ).all()
        ),
        "evidence_items": list(
            session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.run_id == run_id)
                .order_by(EvidenceItem.created_at.asc(), EvidenceItem.id.asc())
            ).all()
        ),
        "findings": list(
            session.scalars(
                select(Finding)
                .where(Finding.run_id == run_id)
                .order_by(Finding.created_at.asc(), Finding.id.asc())
            ).all()
        ),
        "risks": list(
            session.scalars(
                select(Risk)
                .where(Risk.run_id == run_id)
                .order_by(Risk.created_at.asc(), Risk.id.asc())
            ).all()
        ),
        "questions": list(
            session.scalars(
                select(Question)
                .where(Question.run_id == run_id)
                .order_by(Question.created_at.asc(), Question.id.asc())
            ).all()
        ),
        "recommendations": list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.run_id == run_id)
                .order_by(Recommendation.created_at.asc(), Recommendation.id.asc())
            ).all()
        ),
        "quality_scores": list(
            session.scalars(
                select(QualityScore)
                .where(QualityScore.run_id == run_id)
                .order_by(QualityScore.created_at.asc(), QualityScore.id.asc())
            ).all()
        ),
    }
