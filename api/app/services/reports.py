from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun, EvidenceItem, Finding, LoopTurn, Project,
    QualityScore, Question, Recommendation, ReportSnapshot, Risk,
    utc_now,
)
from app.reports.renderer import render_report_markdown
from app.services.audit import record_event
from app.verifiers.package import verify_analysis_package

REVIEW_STATUS_BY_DECISION = {
    "approved": ("approved", "completed"),
    "rejected": ("rejected", "ready"),
    "needs_more": ("needs_more", "ready"),
}
FOLLOWUP_REVIEW_DECISIONS = {"rejected", "needs_more"}


def create_report_snapshot(
        session: Session, project: Project, *, run_id: str | None = None,
) -> ReportSnapshot:
    """从一次已结束的 Loop run 生成报告快照。"""
    run = _get_run_for_report(session, project, run_id)
    if run.status not in {"ready_for_review", "ready_for_review_with_risks"}:
        raise ValueError(f"Run status `{run.status}` is not ready for report review")

    package = build_analysis_package(session, run)
    inventory = _build_inventory(session, project)
    verifier_result = verify_analysis_package(package, inventory)
    title = f"{project.name} 项目调研报告"
    markdown = render_report_markdown(project, package, inventory, verifier_result)
    report = ReportSnapshot(
        project_id=project.id, run_id=run.id,
        status="draft" if verifier_result["passed"] else "blocked",
        title=title, markdown_content=markdown,
        verifier_result_json=verifier_result,
    )
    session.add(report)
    record_event(session, event_type="report.created",
                 message="Report snapshot created", project_id=project.id,
                 payload={"run_id": run.id, "report_id": report.id})
    return report


def create_intelligent_report_snapshot(
        session: Session, project: Project, *, run_id: str | None = None,
) -> ReportSnapshot:
    """智能报告——先生成确定性报告，Module 21 补全 LLM 增强。"""
    return create_report_snapshot(session, project, run_id=run_id)


def review_report_snapshot(
        session: Session, project: Project, report: ReportSnapshot,
        *, decision: str, comment: str | None,
) -> ReportSnapshot:
    if decision not in REVIEW_STATUS_BY_DECISION:
        raise ValueError(f"Unsupported review decision `{decision}`")

    comment = (comment or "").strip()
    if decision in FOLLOWUP_REVIEW_DECISIONS and not comment:
        raise ValueError("Rejected or needs_more reviews require a feedback comment")

    report_status, project_status = REVIEW_STATUS_BY_DECISION[decision]
    report.status = report_status
    report.review_decision = decision
    report.review_comment = comment or None
    report.reviewed_at = utc_now()
    project.status = project_status

    record_event(session, event_type="report.reviewed",
                 message="Report reviewed", project_id=project.id,
                 payload={"report_id": report.id, "decision": decision})
    return report


def get_latest_report(session: Session, project: Project) -> ReportSnapshot | None:
    return session.scalar(
        select(ReportSnapshot)
        .where(ReportSnapshot.project_id == project.id)
        .order_by(ReportSnapshot.created_at.desc(), ReportSnapshot.id.desc())
    )


def _get_run_for_report(session, project, run_id):
    if run_id:
        run = session.get(AnalysisRun, run_id)
        if run is None or run.project_id != project.id:
            raise LookupError("Run not found")
        return run
    run = session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.project_id == project.id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
    )
    if run is None:
        raise LookupError("No analysis run exists for this project")
    return run


def build_analysis_package(session, run):
    return {
        "run": run,
        "turns": _list_by_run(session, LoopTurn, run.id),
        "evidence_items": _list_by_run(session, EvidenceItem, run.id),
        "findings": _list_by_run(session, Finding, run.id),
        "risks": _list_by_run(session, Risk, run.id),
        "questions": _list_by_run(session, Question, run.id),
        "recommendations": _list_by_run(session, Recommendation, run.id),
        "quality_scores": _list_by_run(session, QualityScore, run.id),
    }


def _build_inventory(session, project):
    from app.db.models import CodebaseMap, SourceSnapshot
    return {
        "snapshots": list(session.scalars(
            select(SourceSnapshot)
            .where(SourceSnapshot.project_id == project.id)
            .order_by(SourceSnapshot.created_at.asc())
        ).all()),
        "codebase_maps": list(session.scalars(
            select(CodebaseMap)
            .where(CodebaseMap.project_id == project.id)
            .order_by(CodebaseMap.created_at.asc())
        ).all()),
        "source_bundles": [],
    }


def _list_by_run(session, model, run_id):
    if model is LoopTurn:
        order = (LoopTurn.turn_index.asc(), LoopTurn.id.asc())
    else:
        order = (model.created_at.asc(), model.id.asc())
    return list(session.scalars(
        select(model).where(model.run_id == run_id).order_by(*order)
    ).all())
