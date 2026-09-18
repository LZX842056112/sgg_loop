from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ToolCall, ToolRegistration
from app.db.session import get_session
from app.schemas.tooling import ToolCallRead, ToolRegistrationRead
from app.tools.gateway import list_default_tools
from sqlalchemy import or_, select  # ← import 区追加 or_

router = APIRouter(tags=["tools"])


@router.get("/tools")
def list_tools(session: Session = Depends(get_session)):
    """返回所有可用工具的列表。"""
    return list_default_tools()


@router.get("/projects/{project_id}/runs/{run_id}/tool-calls",
            response_model=list[ToolCallRead])
def list_tool_calls(
        project_id: str, run_id: str,
        session: Session = Depends(get_session),
) -> list:
    statement = (
        select(ToolCall).where(
            ToolCall.project_id == project_id,
            or_(ToolCall.run_id == run_id, ToolCall.run_id.is_(None)),
        ).order_by(ToolCall.created_at.asc(), ToolCall.id.asc())
    )
    return list(session.scalars(statement).all())
