from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EvaluationRun
from app.db.session import get_session
from app.evaluations.runner import run_evaluations
from app.schemas.evaluation import EvaluationRunRead

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/run", response_model=EvaluationRunRead, status_code=status.HTTP_201_CREATED)
# 端点：运行完整评估 harness（POST /evaluations/run）
def run_evaluation_harness(session: Session = Depends(get_session)) -> EvaluationRun:
    return run_evaluations(session)


@router.get("/latest", response_model=EvaluationRunRead)
# 端点：获取最近一次评估结果（GET /evaluations/latest）
def get_latest_evaluation(session: Session = Depends(get_session)) -> EvaluationRun:
    evaluation = session.scalar(
        select(EvaluationRun).order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
    )
    if evaluation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found")
    return evaluation
