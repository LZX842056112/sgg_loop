from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
WorkerSessionLocal = SessionLocal


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def bind_worker_session_to(session: Session) -> None:
    """让本地 worker 复用当前运行环境的数据库 bind。"""
    global WorkerSessionLocal
    WorkerSessionLocal = sessionmaker(
        bind=session.get_bind(), autoflush=False, autocommit=False,
    )


def get_worker_session_factory() -> sessionmaker[Session]:
    return WorkerSessionLocal
