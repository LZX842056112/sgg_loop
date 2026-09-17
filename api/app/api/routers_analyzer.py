"""确定性分析预览路由 — 不依赖 LangGraph、不调 LLM、不做持久化"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.context.builder import build_analysis_context
from app.db.models import Project
from app.db.session import get_session
from app.engine.analyzer import analyze_context

router = APIRouter(prefix="/projects/{project_id}", tags=["analyzer"])


# 按 project_id 查询项目，不存在时抛出 404（FastAPI 路由辅助函数）
def _get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )
    return project


@router.post("/analyze-preview")
def preview_deterministic_analysis(
        project_id: str,
        session: Session = Depends(get_session),
) -> dict:
    """确定性分析预览 — 不写库、不调 LLM、不依赖 LangGraph。

    返回 `analyze_context()` 的 5 类产物：
    evidence, findings, risks, questions, recommendations。

    可用于在第 16 章完成后立即用 curl 验证确定性分析器是否正常工作。
    """
    _get_project_or_404(session, project_id)
    context = build_analysis_context(session, project_id)
    analysis = analyze_context(context)
    return {
        "evidence": analysis.get("evidence", []),
        "findings": analysis.get("findings", []),
        "risks": analysis.get("risks", []),
        "questions": analysis.get("questions", []),
        "recommendations": analysis.get("recommendations", []),
    }
