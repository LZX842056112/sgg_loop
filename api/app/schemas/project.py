from datetime import datetime

from pydantic import BaseModel, Field

from app.research.profiles import DEFAULT_RESEARCH_PROFILE


# create表示用户从外部传入的参数=>应用服务会创建对应的数据到mysql
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    topic: str = Field(min_length=1)
    analysis_goal: str | None = None
    research_profile: str = Field(default=DEFAULT_RESEARCH_PROFILE, min_length=1, max_length=80)
    max_turns: int = Field(default=6, ge=1, le=20)


# read表示应用服务从mysql读取的数据=> 应用服务返回给用户
class ProjectRead(BaseModel):
    id: str
    name: str
    topic: str
    analysis_goal: str | None
    status: str
    research_profile: str
    max_turns: int
    created_at: datetime
    updated_at: datetime

    # 可以让sqlalchemy的orm模型转换为pydantic模型时，从数据库中读取数据
    model_config = {"from_attributes": True}
