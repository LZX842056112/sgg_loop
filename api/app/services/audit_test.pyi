"""
演示 (project_id, sequence) 唯一约束冲突。
运行: python -m app.services.audit_test
"""
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.db.models import AuditEvent
from app.services.audit import record_event


# 确保接下来写入审计表格中的项目ID是存在的
def _ensure_project(session, project_id: str):
    """在projects表格中创建一个project_id的测试数据"""
    from app.db.models import Project
    if not session.get(Project, project_id):
        session.add(Project(id=project_id, name=project_id, topic="测试"))
        session.commit()


# 演示可能发生的错误
def demo_conflict():
    """单线程演示:先插入一条审计数据 然后模拟其他线程插入另外一条sequence号相同的数据"""
    session = SessionLocal()
    pid = "demo_conflict"
    # 创建了一条project_id为demo_conflict的数据
    _ensure_project(session, pid)

    # 正常写入一条数据
    e1 = record_event(session=session, event_type="test", message="第一条", project_id=pid)
    session.commit()

    print(f"[ok] 第一条写入成功:sequence:{e1.sequence}")

    # 手工写入一条 报错出现序列号冲突
    e2 = AuditEvent(
        project_id=pid,
        sequence=e1.sequence,
        event_type="test",
        message="冲突记录"
    )
    session.add(e2)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        print(f"[fail] 唯一约束冲突:{exc.orig}")
    session.close()


# 使用自定义的方法写入 解决序列号冲突的问题
def demo_retry():
    """正常调用:使用record_event自带重试机制 完成序列写入"""
    session = SessionLocal()
    pid = "demo_retry"
    _ensure_project(session, project_id=pid)

    for i in range(3):
        e = record_event(session=session, event_type="test", message=f"第{i + 1}条", project_id=pid)
        session.commit()
        print(f"[ok] 第{i + 1}条写入成功 sequence={e.sequence}")
    session.close()


if __name__ == '__main__':
    # print("场景1:手工构造一个冲突")
    # demo_conflict()

    print("场景2:使用重试机制避免出现冲突问题")
    demo_retry()
