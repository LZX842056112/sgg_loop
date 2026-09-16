from sqlalchemy.orm import Session

from app.db.models import LLMCall


def record_llm_call(
        session: Session,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        report_id: str | None = None,
        profile_id: str | None = None,
        task_type: str,
        provider: str,
        model: str,
        messages: list[dict],
        input_refs: list[str] | None = None,
        output_ref: str | None = None,
        usage: dict | None = None,
        latency_ms: int | None = None,
        status: str,
        error_message: str | None = None,
) -> LLMCall:
    """记录一次 LLM 调用——最小版，只做写入不做预算检查。"""
    import hashlib, json

    prompt_text = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]

    call = LLMCall(
        project_id=project_id,
        run_id=run_id,
        report_id=report_id,
        profile_id=profile_id,
        task_type=task_type,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash,
        input_refs_json=input_refs or [],
        output_ref=output_ref,
        usage_json=usage or {},
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
    )
    session.add(call)
    return call
