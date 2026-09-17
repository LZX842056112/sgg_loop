from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import Project, ReportSnapshot
from app.db.session import get_session
from app.schemas.report import (
    ReportCreate, ReportDiffRead, ReportMarkdownRead,
    ReportReviewCreate, ReportSnapshotRead,
)
from app.services.reports import (
    create_intelligent_report_snapshot, create_report_snapshot,
    get_latest_report, review_report_snapshot,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["reports"])


@router.post("/reports", response_model=ReportSnapshotRead, status_code=201)
def create_report(
        project_id: str, payload: ReportCreate | None = Body(default=None),
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    try:
        report = create_report_snapshot(
            session, project,
            run_id=payload.run_id if payload else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    session.refresh(report)
    return report


@router.post("/reports/intelligent", response_model=ReportSnapshotRead, status_code=201)
def create_intelligent_report(
        project_id: str, payload: ReportCreate | None = Body(default=None),
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    try:
        report = create_intelligent_report_snapshot(
            session, project,
            run_id=payload.run_id if payload else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    session.refresh(report)
    return report


@router.get("/reports/latest", response_model=ReportSnapshotRead)
def get_latest_project_report(
        project_id: str, session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    report = get_latest_report(session, project)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}", response_model=ReportSnapshotRead)
def get_report(
        project_id: str, report_id: str,
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    return _get_report_or_404(session, project_id, report_id)


@router.get("/reports/{report_id}/markdown", response_model=ReportMarkdownRead)
def get_report_markdown(
        project_id: str, report_id: str,
        session: Session = Depends(get_session),
) -> dict:
    report = _get_report_or_404(session, project_id, report_id)
    return {"markdown": report.markdown_content}


@router.post("/reports/{report_id}/review", response_model=ReportSnapshotRead)
def review_report(
        project_id: str, report_id: str, payload: ReportReviewCreate,
        session: Session = Depends(get_session),
) -> ReportSnapshot:
    project = _get_project_or_404(session, project_id)
    report = _get_report_or_404(session, project_id, report_id)
    try:
        review_report_snapshot(
            session, project, report,
            decision=payload.decision, comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.commit()
    session.refresh(report)
    return report


def _get_project_or_404(session, project_id):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_report_or_404(session, project_id, report_id):
    report = session.get(ReportSnapshot, report_id)
    if report is None or report.project_id != project_id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
