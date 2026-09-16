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


import json
from collections.abc import Iterable
from time import monotonic, sleep

from app.db.models import RunJob

TERMINAL_RUN_EVENTS = {"run_completed", "run_failed", "run_cancelled"}


# ── SSE 编码 ──

def encode_sse_event(event: RunEvent) -> str:
    """把 RunEvent ORM 对象编码为 SSE 帧。"""
    payload = {
        "id": event.id,
        "project_id": event.project_id,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "created_at": event.created_at.isoformat(),
        **event.payload_json,
    }
    return (
        f"id: {event.sequence}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def encode_sse(event_name: str, payload: dict) -> str:
    """用指定事件名编码一条 SSE 帧。"""
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def encode_many_sse(events: Iterable[RunEvent]) -> str:
    """批量编码多条事件。"""
    return "".join(encode_sse_event(e) for e in events)


def encode_keepalive_sse() -> str:
    """SSE 心跳帧——以冒号开头的行是 SSE 注释，不算事件。"""
    return ": keepalive\n\n"


# ── 实时流式推送 ──

def run_has_active_job(session: Session, run_id: str) -> bool:
    """检查 run 是否有排队中或运行中的 job。"""
    return (
            session.scalar(
                select(RunJob.id)
                .where(
                    RunJob.run_id == run_id,
                    RunJob.status.in_({"queued", "running"}),
                )
                .limit(1)
            )
            is not None
    )


def stream_run_events_live(
        session_factory,
        *,
        project_id: str,
        run_id: str,
        after_sequence: int = 0,
        poll_interval_seconds: float = 0.5,
        keepalive_seconds: float = 10.0,
):
    """持续推送运行事件——每次轮询使用新 session，支持断线补发。

    遇到终态事件（run_completed/run_failed/run_cancelled）直接结束；
    没有活动 job 时也结束，避免已完成 run 一直等待。
    """
    last_sequence = max(0, after_sequence)
    last_keepalive_at = monotonic()

    while True:
        with session_factory() as session:
            events = list_run_events(session, project_id, run_id, last_sequence)
            if events:
                for event in events:
                    yield encode_sse_event(event)
                    last_sequence = event.sequence
                    last_keepalive_at = monotonic()
                    if event.event_type in TERMINAL_RUN_EVENTS:
                        return
                continue

            if not run_has_active_job(session, run_id):
                return

        now = monotonic()
        if now - last_keepalive_at >= keepalive_seconds:
            yield encode_keepalive_sse()
            last_keepalive_at = now
        sleep(poll_interval_seconds)
