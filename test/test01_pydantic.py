from pydantic import BaseModel, Field


class UserBaseModel(BaseModel):
    name: str = Field(default="张三", max_length=10, min_length=2)
    age: int = Field(default=18, ge=0, le=120)


# user = UserBaseModel(age='40')
user = UserBaseModel()
print(user)
