STARTABLE_PROJECT_STATUSES = {
    "draft", "ready", "ready_for_review",
    "ready_for_review_with_risks", "failed",
}


def can_start_run(project_status: str) -> bool:
    """判断当前项目状态是否允许启动新的分析运行。"""
    return project_status in STARTABLE_PROJECT_STATUSES


def ensure_can_start_run(project_status: str) -> None:
    """如果不允许启动，直接抛异常。"""
    if not can_start_run(project_status):
        raise ValueError(
            f"Cannot start a run while project status is {project_status}"
        )


def has_open_high_impact_question(questions: list[dict]) -> bool:
    """是否有未解决的高影响问题——如果有，运行需要暂停等待用户输入。"""
    return any(
        q.get("status") == "open" and q.get("impact") == "high"
        for q in questions
    )


def decide_terminal_state(
        snapshots: list[dict],
        findings: list[dict],
        risks: list[dict],
        questions: list[dict],
        recommendations: list[dict],
        quality_score: dict,
) -> dict:
    """根据分析结果决定运行的终态——不依赖 LLM 自评。"""
    if not snapshots:
        return {"status": "failed", "reason": "没有可用的输入源采集快照。"}
    if has_open_high_impact_question(questions):
        return {"status": "paused_for_input", "reason": "存在高影响开放问题，需要用户输入。"}
    if not findings or not recommendations:
        return {"status": "failed", "reason": "本次运行没有形成发现和建议。"}

    overall_score = int(quality_score.get("overall_score", 0))
    if overall_score >= 80 and not risks:
        return {"status": "ready_for_review", "reason": "质量分达到评审阈值，且未记录风险。"}
    return {
        "status": "ready_for_review_with_risks",
        "reason": "分析包可进入评审，但仍存在评分缺口或已记录风险。",
    }
