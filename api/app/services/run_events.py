from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import RunEvent

RUN_EVENT_SEQUENCE_RETRIES = 5


def _next_sequence(session: Session, run_id: str) -> int:
    current = session.scalar(
        select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
    )
    return int(current or 0) + 1


def _is_sequence_conflict(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "uq_run_events_run_sequence" in message or (
            "unique" in message and "run_events" in message and "sequence" in message
    )


def record_run_event(
        session: Session,
        project_id: str,
        run_id: str,
        event_type: str,
        payload: dict | None = None,
) -> RunEvent:
    """记录运行事件——带 savepoint 的序号重试。"""
    last_conflict: IntegrityError | None = None
    for _ in range(RUN_EVENT_SEQUENCE_RETRIES):
        event = RunEvent(
            project_id=project_id,
            run_id=run_id,
            event_type=event_type,
            sequence=_next_sequence(session, run_id),
            payload_json=payload or {},
        )
        try:
            with session.begin_nested():
                session.add(event)
                session.flush()
            return event
        except IntegrityError as exc:
            if event in session:
                session.expunge(event)
            if not _is_sequence_conflict(exc):
                raise
            last_conflict = exc
    raise RuntimeError("Failed to allocate a unique run event sequence") from last_conflict


def list_run_events(
        session: Session, project_id: str, run_id: str, after_sequence: int = 0,
) -> list[RunEvent]:
    """按序号列出运行事件。"""
    return list(
        session.scalars(
            select(RunEvent)
            .where(
                RunEvent.project_id == project_id,
                RunEvent.run_id == run_id,
                RunEvent.sequence > after_sequence,
            )
            .order_by(RunEvent.sequence.asc(), RunEvent.id.asc())
        ).all()
    )
