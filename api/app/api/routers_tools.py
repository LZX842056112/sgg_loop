from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ToolCall, ToolRegistration
from app.db.session import get_session
from app.schemas.tooling import ToolCallRead, ToolRegistrationRead

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolRegistrationRead])
def list_tools(session: Session = Depends(get_session)) -> list:
    statement = select(ToolRegistration).order_by(
        ToolRegistration.name.asc(), ToolRegistration.id.asc()
    )
    return list(session.scalars(statement).all())


@router.get("/projects/{project_id}/runs/{run_id}/tool-calls",
            response_model=list[ToolCallRead])
def list_tool_calls(
        project_id: str, run_id: str,
        session: Session = Depends(get_session),
) -> list:
    statement = (
        select(ToolCall)
        .where(ToolCall.project_id == project_id, ToolCall.run_id == run_id)
        .order_by(ToolCall.created_at.asc(), ToolCall.id.asc())
    )
    return list(session.scalars(statement).all())
