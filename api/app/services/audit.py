from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

AUDIT_EVENT_SEQUENCE_RETRIES = 5


# 要保证同一个项目中  所有的审计事件序列号都是单调递增的 且不能重复
def record_event(
        session: Session,
        *,
        event_type: str,
        message: str,
        project_id: str | None = None,
        payload: dict | None = None,
        actor_id: str = "local-user"
) -> AuditEvent:
    """ 所有关键的动作都需要落盘审计事件"""
    last_conflict: IntegrityError | None = None
    for _ in range(AUDIT_EVENT_SEQUENCE_RETRIES):
        event = AuditEvent(
            project_id=project_id,
            sequence=next_project_event_sequence(session=session, project_id=project_id),
            event_type=event_type,
            message=message,
            actor_id=actor_id,
            payload_json=payload
        )
        try:
            with session.begin_nested():
                session.add(event)
                session.flush()
            # 数据正确写入 直接跳出运行 直接退出
            return event
        except IntegrityError as exc:
            # 报错首先要擦除对应数据
            if event in session:
                session.expunge(event)
            if not is_audit_evnet_sequence_conflict(exc=exc):
                raise
            last_conflict = exc
    raise RuntimeError("Failed to allocate a unique audit event sequence") from last_conflict


# 是否出现了同一个项目多线程序列号冲突的问题
def is_audit_evnet_sequence_conflict(exc: IntegrityError) -> bool:
    """判断数据库返回信息是否是报错说是项目同序列号问题"""
    message = str(getattr(exc, "orig", exc)).lower()
    return "uq_audit_events_project_sequence" in message or (
            "unique" in message and "audit_events" in message and "sequence" in message
    )


# 保证同一个项目读取到之后生成单调递增的序列号
def next_project_event_sequence(session: Session, project_id: str | None) -> int:
    """按照项目生成单调递增的序列号"""
    # 其他的审计事件
    if project_id is None:
        return 1

    # 1. 刷新数据库
    session.flush()
    latest_sequence = session.scalar(
        select(func.max(AuditEvent.sequence)).where(AuditEvent.project_id == project_id)
    )
    return int(latest_sequence or 0) + 1
