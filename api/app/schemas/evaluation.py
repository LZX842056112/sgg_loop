from datetime import datetime

from pydantic import BaseModel


# 评估运行结果的响应 Schema
class EvaluationRunRead(BaseModel):
    id: str
    status: str
    summary_json: dict
    case_results_json: list
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
