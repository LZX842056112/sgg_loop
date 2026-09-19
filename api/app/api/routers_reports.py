from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.models import Project, ReportSnapshot
from app.db.session import get_session
from app.reports.diff import build_report_package_snapshot, diff_report_snapshots
from app.reports.pdf import render_markdown_pdf
from app.schemas.report import (
    ReportCreate,
    ReportDiffRead,
    ReportMarkdownRead,
    ReportReviewCreate,
    ReportSnapshotRead,
)
from app.services.reports import (
    create_intelligent_report_snapshot,
    create_report_snapshot,
    get_latest_report,
    review_report_snapshot,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["reports"])


@router.post("/reports", response_model=ReportSnapshotRead, status_code=status.HTTP_201_CREATED)
# 端点：生成确定性报告快照（POST /reports）
def create_report(
        project_id: str,
        payload: ReportCreate | None = Body(default=None),
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    try:
        report = create_report_snapshot(session, project, run_id=payload.run_id if payload else None)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(report)
    return report


@router.post("/reports/intelligent", response_model=ReportSnapshotRead, status_code=status.HTTP_201_CREATED)
# 端点：生成智能报告——确定性报告 + 受证据约束的 LLM 增强段落
def create_intelligent_report(
        project_id: str,
        payload: ReportCreate | None = Body(default=None),
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    try:
        report = create_intelligent_report_snapshot(session, project, run_id=payload.run_id if payload else None)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    session.refresh(report)
    return report


@router.get("/reports/latest", response_model=ReportSnapshotRead)
# 端点：获取项目最新报告（GET /reports/latest）
def get_latest_project_report(project_id: str, session: Session = Depends(get_session)) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    report = get_latest_report(session, project)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}", response_model=ReportSnapshotRead)
# 端点：按 id 获取报告（GET /reports/{report_id}）
def get_report(project_id: str, report_id: str, session: Session = Depends(get_session)) -> ReportSnapshot:
    return _get_report_or_404(session, project_id, report_id)


@router.get("/reports/{report_id}/markdown", response_model=ReportMarkdownRead)
# 端点：获取报告 Markdown 原文（GET /reports/{report_id}/markdown）
def get_report_markdown(project_id: str, report_id: str, session: Session = Depends(get_session)) -> dict[str, str]:
    report = _get_report_or_404(session, project_id, report_id)
    return {"markdown": report.markdown_content}


@router.get("/reports/{report_id}/export.pdf")
# 端点：导出 PDF 附件（GET /reports/{report_id}/export.pdf）
def export_report_pdf(project_id: str, report_id: str, session: Session = Depends(get_session)) -> Response:
    report = _get_report_or_404(session, project_id, report_id)
    pdf_content = render_markdown_pdf(title=report.title, markdown=report.markdown_content)
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report.id}.pdf"'},
    )


@router.get("/reports/{report_id}/export.md")
# 端点：导出 Markdown 文件附件（GET /reports/{report_id}/export.md）
def export_report_markdown(project_id: str, report_id: str, session: Session = Depends(get_session)) -> Response:
    report = _get_report_or_404(session, project_id, report_id)
    return Response(
        content=report.markdown_content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report.id}.md"'},
    )


@router.get("/reports/{report_id}/diff", response_model=ReportDiffRead)
# 端点：对比两个报告版本的差异（GET /reports/{report_id}/diff）
def get_report_diff(
        project_id: str,
        report_id: str,
        base_report_id: str,
        session: Session = Depends(get_session),
) -> dict:
    _get_project_or_404(session, project_id)
    target_report = _get_report_or_404(session, project_id, report_id)
    base_report = _get_report_or_404(session, project_id, base_report_id)
    # 按报告创建时间截断 run 产物，避免评审反馈等后写入数据污染历史版本 diff。
    base_package = build_report_package_snapshot(session, base_report)
    target_package = build_report_package_snapshot(session, target_report)
    return {
        "base_report_id": base_report.id,
        "target_report_id": target_report.id,
        "diff": diff_report_snapshots(base_package, target_package),
    }


@router.post("/reports/{report_id}/review", response_model=ReportSnapshotRead)
# 端点：评审报告（approved / rejected / needs_more）
def review_report(
        project_id: str,
        report_id: str,
        payload: ReportReviewCreate,
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    report = _get_report_or_404(session, project_id, report_id)
    try:
        review_report_snapshot(
            session,
            project,
            report,
            decision=payload.decision,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    session.refresh(report)
    return report


# 按 id 查询项目，不存在时抛出 404
def _get_project_or_404(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# 按 id 查询报告并校验归属项目，不存在或不属于该项目时抛出 404
def _get_report_or_404(session: Session, project_id: str, report_id: str) -> ReportSnapshot:
    report = session.get(ReportSnapshot, report_id)
    if report is None or report.project_id != project_id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
