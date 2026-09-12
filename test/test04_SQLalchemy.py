from sqlalchemy.orm import Mapped, mapped_column, Session, DeclarativeBase
from sqlalchemy import String, select


class Base(DeclarativeBase):
    pass


# 2.创建表
class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)


# 3.创建引擎
from sqlalchemy import create_engine

engine = create_engine("mysql+pymysql://root:123456@localhost:3306/loop_engineering", echo=True)

# 4.创建表格
Base.metadata.create_all(engine)

# 5.创建会话
with Session(engine) as session:
    # 5.1创建一条数据
    new_user = User(id='1', name='张三')
    session.add(new_user)
    session.commit()

    # 5.2查询数据
    result = session.scalars(
        select(User)
        .where(User.id == '1')
        .order_by(User.id.asc())
    ).first()
    print(result.id, result.name)

    # 5.3 修改数据
    result.name = '李四'
    session.add(result)
    session.commit()

    # 5.4删除数据
    session.delete(result)
    session.commit()
    session.flush()

from sqlalchemy.orm import Session, sessionmaker
from collections.abc import Generator

# 创建 session 工厂
SessionLocal = sessionmaker(bind=engine, autoflush=False)


# 在 FastAPI 中使用依赖注入管理 session 生命周期
def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# gen = get_session()
# session = next(gen)
