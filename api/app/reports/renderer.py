from app.verifiers.package import as_list, value_of


def render_report_markdown(project, package, inventory, verifier_result) -> str:
    """把 Analysis Package 渲染成稳定的中文 Markdown 报告。"""
    lines = [
        f"# {text(value_of(project, 'name', '项目'))} 项目调研报告", "",
        "## 项目概览", "",
        f"- 项目 ID：`{text(value_of(project, 'id', 'unknown'))}`",
        f"- 主题：{text(value_of(project, 'topic', ''))}",
        f"- 分析目标：{text(value_of(project, 'analysis_goal', '未填写'))}",
        f"- 项目状态：`{status_label(text(value_of(project, 'status', 'unknown')))}`", "",
        "## 校验摘要", "",
        f"- 是否通过：`{bool_label(bool(verifier_result.get('passed', False)))}`",
        f"- 风险等级：`{risk_label(text(verifier_result.get('risk_level', 'unknown')))}`",
        f"- 摘要：{text(verifier_result.get('summary', ''))}", "",
    ]
    lines.extend(_render_executive_summary(project, package, verifier_result))
    lines.extend(_render_findings(package))
    lines.extend(_render_risks(package))
    lines.extend(_render_evidence(package))
    lines.extend(_render_questions(package))
    lines.extend(_render_recommendations(package))
    return "\n".join(lines).strip() + "\n"


def _render_executive_summary(project, package, verifier_result) -> list[str]:
    findings_count = len(as_list(package.get("findings")))
    risks_count = len(as_list(package.get("risks")))
    passed = bool(verifier_result.get("passed", False))
    risk_level = text(verifier_result.get("risk_level", "unknown"))
    summary = text(verifier_result.get("summary", ""))
    conclusion = f"{bool_label(passed)}，风险等级：{risk_label(risk_level)}"
    if summary:
        conclusion = f"{conclusion}；{summary}"
    return [
        "## 执行摘要", "",
        f"- 项目：{text(value_of(project, 'name', '项目'))}",
        f"- 发现数量：`{findings_count}`", f"- 风险数量：`{risks_count}`",
        f"- 校验结论：{conclusion}", "",
    ]


def _render_findings(package) -> list[str]:
    lines = ["## 发现", ""]
    items = as_list(package.get("findings"))
    if not items:
        lines.append("- 暂无发现。")
    for f in items:
        lines.append(f"- {text(value_of(f, 'title', '未命名发现'))}")
        lines.append(f"  - 类别：`{text(value_of(f, 'category', 'unknown'))}`")
        lines.append(f"  - 影响：`{risk_label(text(value_of(f, 'impact_level', 'unknown')))}`")
        lines.append(f"  - 摘要：{text(value_of(f, 'summary', ''))}")
        lines.append(f"  - 证据引用：{_join_refs(value_of(f, 'evidence_refs_json', []))}")
    lines.append("")
    return lines


def _render_risks(package) -> list[str]:
    lines = ["## 风险登记", ""]
    items = as_list(package.get("risks"))
    if not items:
        lines.append("- 暂无登记风险。")
    for r in items:
        lines.append(f"- {text(value_of(r, 'title', '未命名风险'))}")
        lines.append(f"  - 严重程度：`{risk_label(text(value_of(r, 'severity', 'unknown')))}`")
        lines.append(f"  - 摘要：{text(value_of(r, 'summary', ''))}")
        lines.append(f"  - 缓解建议：{text(value_of(r, 'mitigation', ''))}")
    lines.append("")
    return lines


def _render_evidence(package) -> list[str]:
    lines = ["## 证据", ""]
    items = as_list(package.get("evidence_items"))
    if not items:
        lines.append("- 暂无证据项。")
    for e in items:
        lines.append(f"- `{text(value_of(e, 'id', 'evidence'))}` {text(value_of(e, 'title', '证据'))}")
        lines.append(f"  - 类型：`{text(value_of(e, 'evidence_type', 'unknown'))}`")
        lines.append(f"  - 摘要：{text(value_of(e, 'summary', ''))}")
    lines.append("")
    return lines


def _render_questions(package) -> list[str]:
    lines = ["## 开放问题", ""]
    items = as_list(package.get("questions"))
    if not items:
        lines.append("- 暂无开放问题。")
    for q in items:
        lines.append(f"- {text(value_of(q, 'prompt', '未命名问题'))}")
        lines.append(f"  - 状态：`{status_label(text(value_of(q, 'status', 'unknown')))}`")
        lines.append(f"  - 影响：`{risk_label(text(value_of(q, 'impact', 'unknown')))}`")
        answer = value_of(q, "answer_text")
        if answer:
            lines.append(f"  - 回答：{text(answer)}")
    lines.append("")
    return lines


def _render_recommendations(package) -> list[str]:
    lines = ["## 建议", ""]
    items = as_list(package.get("recommendations"))
    if not items:
        lines.append("- 暂无建议。")
    for r in items:
        lines.append(f"- {text(value_of(r, 'summary', '建议'))}")
        lines.append(f"  - 依据：{text(value_of(r, 'rationale', ''))}")
        lines.append(f"  - 可信度：`{text(value_of(r, 'confidence', 'unknown'))}`")
    lines.append("")
    return lines


# ── 工具函数 ──

def _join_refs(values) -> str:
    items = [str(v) for v in as_list(values) if v]
    return "，".join(items) if items else "无"


def text(value) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def bool_label(value: bool) -> str:
    return "是" if value else "否"


def risk_label(value: str) -> str:
    return {"low": "低", "medium": "中", "high": "高", "critical": "严重", "unknown": "未知"}.get(value, value)


def status_label(value: str) -> str:
    return {
        "draft": "草稿", "ready": "就绪", "running": "运行中",
        "paused_for_input": "等待输入", "pending": "待处理", "partial": "部分完成",
        "ready_for_review": "待评审", "ready_for_review_with_risks": "带风险待评审",
        "completed": "已完成", "failed": "失败", "blocked": "存在阻塞",
        "approved": "已通过", "rejected": "已驳回", "needs_more": "要求补充",
        "answered": "已回答", "open": "待回答", "collected": "已采集", "unknown": "未知",
    }.get(value, value)
