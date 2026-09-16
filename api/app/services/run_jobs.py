from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RunJob

ACTIVE_JOB_STATUSES = {"queued", "running"}


def create_run_job(
        session: Session,
        project_id: str,
        run_id: str,
        job_type: str,
        payload: dict | None = None,
        queue_name: str = "default",
) -> RunJob:
    """创建后台任务——相同 run/type 的 active job 会复用，避免重复入队。"""
    existing = session.scalar(
        select(RunJob)
        .where(
            RunJob.run_id == run_id,
            RunJob.job_type == job_type,
            RunJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(RunJob.created_at.desc(), RunJob.id.desc())
    )
    if existing is not None:
        return existing

    job = RunJob(
        project_id=project_id,
        run_id=run_id,
        job_type=job_type,
        payload_json=payload or {},
        queue_name=queue_name,
    )
    session.add(job)
    session.flush()
    return job


def cancel_run_jobs(session: Session, run_id: str) -> list[RunJob]:
    """取消同一 run 上的活跃任务。"""
    jobs = list(
        session.scalars(
            select(RunJob).where(
                RunJob.run_id == run_id,
                RunJob.status.in_(ACTIVE_JOB_STATUSES),
            )
        ).all()
    )
    for job in jobs:
        job.status = "cancelled"
        job.locked_by = None
        job.locked_at = None
        job.locked_until = None
        job.heartbeat_at = None
    return jobs
