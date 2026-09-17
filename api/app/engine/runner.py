from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisRun, EvidenceItem, Finding, LoopTurn, Project,
    QualityScore, Question, Recommendation, Risk, RunJob,
)
from app.db.session import bind_worker_session_to
from app.engine.state_machine import ensure_can_start_run
from app.services.audit import record_event
from app.services.run_events import record_run_event
from app.services.run_jobs import create_run_job


def initialize_run(session: Session, project: Project) -> AnalysisRun:
    """创建一次 Loop 运行——不立即执行，只做状态校验和初始化。"""
    ensure_can_start_run(project.status)
    run = AnalysisRun(
        project_id=project.id,
        status="running",
        max_turns=project.max_turns,
    )
    project.status = "running"
    session.add(run)
    session.flush()
    run.thread_id = f"run:{run.id}"
    record_event(
        session,
        event_type="run.started",
        message="Loop 运行已启动",
        project_id=project.id,
        payload={"run_id": run.id},
    )
    return run


def enqueue_run(
        session: Session,
        project: Project,
        job_type: str = "start",
        payload: dict | None = None,
) -> tuple[AnalysisRun, RunJob]:
    """创建后台运行任务——HTTP 只负责登记，实际执行由 Worker 接管。

    这是 durable runtime 的入口：浏览器断开不影响已排队的 run。
    """
    ensure_can_start_run(project.status)
    bind_worker_session_to(session)

    run = AnalysisRun(
        project_id=project.id,
        status="queued",
        max_turns=project.max_turns,
        execution_mode="background",
    )
    project.status = "queued"
    session.add(run)
    session.flush()
    run.thread_id = f"run:{run.id}"

    job = create_run_job(session, project.id, run.id, job_type, payload)
    record_run_event(
        session, project.id, run.id, "run_queued",
        {"status": run.status, "job_id": job.id},
    )
    return run, job


# ── 以下方法在 Module 18 补全 LangGraph 引擎后启用 ──
def append_turn(
        session: Session, run: AnalysisRun, project: Project,
        node_name: str, action: str, observation: str,
        metadata: dict | None = None,
) -> LoopTurn:
    """记录一次 Loop 轮次。"""
    turn = LoopTurn(
        run_id=run.id, project_id=project.id,
        turn_index=run.current_turn + 1,
        node_name=node_name, action=action,
        observation=observation, status="completed",
        metadata_json=metadata or {},
    )
    session.add(turn)
    session.flush()
    run.current_turn = turn.turn_index
    return turn


def start_run(session: Session, project: Project) -> AnalysisRun:
    """创建并同步执行一次 Loop（用于测试和 Demo 场景）。"""
    run = initialize_run(session, project)
    execute_run(session, project, run)
    return run


def execute_run(session: Session, project: Project, run: AnalysisRun) -> None:
    """执行一次 Loop——真实编排由 LangGraph StateGraph 负责。"""
    # from app.engine.langgraph_runner import execute_run_graph

    project_id = project.id
    run_id = run.id
    if not run.thread_id:
        run.thread_id = f"run:{run.id}"
    thread_id = run.thread_id
    session.commit()  # 先提交 run，让 checkpoint 能引用已存在的 run
    # execute_run_graph(session, project_id, run_id, thread_id)


def get_run_package(session: Session, project_id: str, run_id: str) -> dict:
    """组装一次运行的完整分析包——所有产出物。"""
    run = session.get(AnalysisRun, run_id)
    if run is None:
        return None

    return {
        "run": run,
        "turns": list(
            session.scalars(
                select(LoopTurn)
                .where(LoopTurn.run_id == run_id)
                .order_by(LoopTurn.turn_index.asc(), LoopTurn.id.asc())
            ).all()
        ),
        "evidence_items": list(
            session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.run_id == run_id)
                .order_by(EvidenceItem.created_at.asc(), EvidenceItem.id.asc())
            ).all()
        ),
        "findings": list(
            session.scalars(
                select(Finding)
                .where(Finding.run_id == run_id)
                .order_by(Finding.created_at.asc(), Finding.id.asc())
            ).all()
        ),
        "risks": list(
            session.scalars(
                select(Risk)
                .where(Risk.run_id == run_id)
                .order_by(Risk.created_at.asc(), Risk.id.asc())
            ).all()
        ),
        "questions": list(
            session.scalars(
                select(Question)
                .where(Question.run_id == run_id)
                .order_by(Question.created_at.asc(), Question.id.asc())
            ).all()
        ),
        "recommendations": list(
            session.scalars(
                select(Recommendation)
                .where(Recommendation.run_id == run_id)
                .order_by(Recommendation.created_at.asc(), Recommendation.id.asc())
            ).all()
        ),
        "quality_scores": list(
            session.scalars(
                select(QualityScore)
                .where(QualityScore.run_id == run_id)
                .order_by(QualityScore.created_at.asc(), QualityScore.id.asc())
            ).all()
        ),
    }


def resume_run(session: Session, project: Project, run: AnalysisRun) -> AnalysisRun:
    """恢复暂停的运行——仅 paused_for_input 状态允许。"""
    if run.status != "paused_for_input":
        raise ValueError("Only paused runs can be resumed")

    # 确保 thread_id 存在
    if not run.thread_id:
        run.thread_id = f"run:{run.id}"
    thread_id = run.thread_id

    project.status = "running"
    run.status = "running"
    run.resume_count += 1

    record_event(
        session,
        event_type="run.resumed",
        message="Loop 运行已继续",
        project_id=project.id,
        payload={"run_id": run.id},
    )
    session.commit()

    # TODO 调用 LangGraph 引擎继续执行

    return run


from app.db.models import (
    EvidenceItem, Finding, QualityScore, Question, Recommendation, Risk,
)

NODE_ORDER = [
    "load_state",
    "build_context",
    "analyze_sources",
    "llm_analyze_sources",
    "update_analysis",
    "verify_package",
    "llm_verify_package",
    "decide_next_state",
    "persist_state",
]


# 查询上一轮运行的质量分（overall_score），用于计算本次的 score_delta
def latest_previous_score(session: Session, run: AnalysisRun) -> int | None:
    statement = (
        select(QualityScore.overall_score)
        .where(QualityScore.run_id == run.id)
        .order_by(QualityScore.created_at.desc(), QualityScore.id.desc())
    )
    return session.scalar(statement)


# 把分析产物 dict 持久化到 EvidenceItem/Finding/Risk/Question/Recommendation 五张表，返回落库摘要
def persist_analysis_artifacts(
        session: Session,
        project: Project,
        run: AnalysisRun,
        analysis: dict,
) -> dict:
    evidence_ref_map: dict[str, str] = {}
    persisted_evidence: list[dict] = []
    for evidence in analysis["evidence"]:
        item = EvidenceItem(
            project_id=project.id,
            run_id=run.id,
            source_id=evidence.get("source_id"),
            title=evidence["title"],
            summary=evidence["summary"],
            evidence_type=evidence["evidence_type"],
            reference=evidence.get("reference"),
            confidence=evidence.get("confidence", 80),
            metadata_json=evidence.get("metadata", {}),
        )
        session.add(item)
        session.flush()
        evidence_ref_map[evidence["client_ref"]] = item.id
        persisted_evidence.append({"id": item.id})

    persisted_findings: list[dict] = []
    for finding in analysis["findings"]:
        evidence_refs = [evidence_ref_map[ref] for ref in finding.get("evidence_refs", []) if ref in evidence_ref_map]
        session.add(
            Finding(
                project_id=project.id,
                run_id=run.id,
                title=finding["title"],
                summary=finding["summary"],
                category=finding["category"],
                impact_level=finding["impact_level"],
                confidence=finding.get("confidence", 75),
                evidence_refs_json=evidence_refs,
                metadata_json=finding.get("metadata", {}),
            )
        )
        persisted_findings.append({"evidence_refs": evidence_refs})

    persisted_risks: list[dict] = []
    for risk in analysis["risks"]:
        evidence_refs = [evidence_ref_map[ref] for ref in risk.get("evidence_refs", []) if ref in evidence_ref_map]
        session.add(
            Risk(
                project_id=project.id,
                run_id=run.id,
                title=risk["title"],
                summary=risk["summary"],
                severity=risk["severity"],
                mitigation=risk["mitigation"],
                evidence_refs_json=evidence_refs,
                metadata_json=risk.get("metadata", {}),
            )
        )
        persisted_risks.append({"severity": risk["severity"], "mitigation": risk["mitigation"],
                                "evidence_refs": evidence_refs})

    persisted_questions: list[dict] = []
    for question in analysis["questions"]:
        existing_answered = find_answered_question(session, project.id, question)
        if existing_answered is not None:
            persisted_questions.append({"status": existing_answered.status, "impact": existing_answered.impact})
            continue
        session.add(
            Question(
                project_id=project.id,
                run_id=run.id,
                prompt=question["prompt"],
                reason=question["reason"],
                impact=question["impact"],
                status=question.get("status", "open"),
                metadata_json=question.get("metadata", {}),
            )
        )
        persisted_questions.append({"status": question.get("status", "open"), "impact": question["impact"]})

    persisted_recommendations: list[dict] = []
    for recommendation in analysis["recommendations"]:
        session.add(
            Recommendation(
                project_id=project.id,
                run_id=run.id,
                summary=recommendation["summary"],
                rationale=recommendation["rationale"],
                confidence=recommendation.get("confidence", 70),
                next_steps_json=recommendation.get("next_steps", []),
                metadata_json=recommendation.get("metadata", {}),
            )
        )
        persisted_recommendations.append({"summary": recommendation["summary"],
                                          "confidence": recommendation.get("confidence", 70)})
    session.flush()
    return {
        "evidence": persisted_evidence,
        "findings": persisted_findings,
        "risks": persisted_risks,
        "questions": persisted_questions,
        "recommendations": persisted_recommendations,
    }


# 按 prompt 查找该项目已回答过的问题，避免 resume 后重复创建同一问题
def find_answered_question(session: Session, project_id: str, question: dict) -> Question | None:
    statement = (
        select(Question)
        .where(
            Question.project_id == project_id,
            Question.prompt == question["prompt"],
            Question.status == "answered",
        )
        .order_by(Question.answered_at.desc(), Question.id.desc())
    )
    return session.scalar(statement)
