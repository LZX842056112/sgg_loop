from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import LLMCall, LLMProfile
from app.db.session import get_session
from app.llm.openai_compatible import OpenAICompatibleClient
from app.llm.profiles import safe_profile_dict
from app.llm.router import LLMRouter
from app.schemas.llm import LLMCallRead, LLMProfileCreate, LLMProfileRead, LLMProfileUpdate

router = APIRouter(prefix="/llm", tags=["llm"])


def _build_client_from_settings(settings: Settings) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key_required=settings.llm_api_key_required,
        timeout_seconds=settings.llm_timeout_seconds,
    )


# ── Provider 状态 ──

@router.get("/provider")
def get_provider_status(settings: Settings = Depends(get_settings)) -> dict:
    """返回 .env 中 LLM Provider 的配置状态，不包含 API key。"""
    return _build_client_from_settings(settings).status()


# ── Profile CRUD ──

@router.get("/profiles", response_model=list[LLMProfileRead])
def list_llm_profiles(session: Session = Depends(get_session)) -> list[dict]:
    statement = select(LLMProfile).order_by(
        LLMProfile.updated_at.desc(), LLMProfile.id.desc()
    )
    return [safe_profile_dict(p) for p in session.scalars(statement).all()]


@router.post("/profiles", response_model=LLMProfileRead, status_code=201)
def create_llm_profile(
        payload: LLMProfileCreate, session: Session = Depends(get_session),
) -> dict:
    profile = LLMProfile(**payload.model_dump())
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return safe_profile_dict(profile)


@router.patch("/profiles/{profile_id}", response_model=LLMProfileRead)
def update_llm_profile(
        profile_id: str,
        payload: LLMProfileUpdate,
        session: Session = Depends(get_session),
) -> dict:
    profile = session.get(LLMProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="LLM profile not found")

    updates = payload.model_dump(exclude_unset=True)
    # 关键字段不允许设为 null
    non_nullable = {
        "name", "provider", "base_url", "model", "api_key_required",
        "max_tokens", "temperature", "timeout_seconds", "enabled",
    }
    null_fields = sorted(
        f for f in non_nullable
        if updates.get(f) is None and f in updates
    )
    if null_fields:
        raise HTTPException(
            status_code=422,
            detail=f"{', '.join(null_fields)} cannot be null",
        )

    for key, value in updates.items():
        setattr(profile, key, value)
    session.commit()
    session.refresh(profile)
    return safe_profile_dict(profile)


# ── 冒烟测试 ──

@router.post("/profiles/{profile_id}/smoke-test")
def smoke_test_profile(
        profile_id: str, session: Session = Depends(get_session),
) -> dict:
    """对指定 Profile 做连通性测试。"""
    profile = session.get(LLMProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="LLM profile not found")

    result = LLMRouter(session).chat(
        task_type=profile.task_type,
        profile_id=profile.id,
        messages=[
            {"role": "system", "content": "你是连通性检测助手，只用一句中文回复。"},
            {"role": "user", "content": "请回复一句话，确认当前 LLM 配置可访问。"},
        ],
        required=False,
    )
    session.commit()
    return {
        "status": result["status"],
        "call_id": result["call_id"],
        "text_excerpt": result["text"][:240],
    }


@router.post("/smoke-test")
def smoke_test_global(
        settings: Settings = Depends(get_settings),
) -> dict:
    """使用 .env 中的 Provider 配置做连通性测试。"""
    client = _build_client_from_settings(settings)
    if not client.status()["configured"]:
        raise HTTPException(status_code=503, detail="LLM provider is not configured")

    result = client.chat(
        messages=[
            {"role": "system", "content": "你是连通性检测助手，只用一句中文回复。"},
            {"role": "user", "content": "请回复一句话，确认当前 LLM 配置可访问。"},
        ],
        max_tokens=128,
        temperature=0.2,
    )
    return {
        "provider": result["provider"],
        "model": result["model"],
        "status": "ok",
        "text_excerpt": result["text"][:240],
        "usage": result["usage"],
    }


# ── 调用记录 ──

@router.get("/calls", response_model=list[LLMCallRead])
def list_llm_calls(
        project_id: str | None = None,
        run_id: str | None = None,
        session: Session = Depends(get_session),
) -> list[LLMCall]:
    statement = select(LLMCall)
    if project_id is not None:
        statement = statement.where(LLMCall.project_id == project_id)
    if run_id is not None:
        statement = statement.where(LLMCall.run_id == run_id)
    statement = statement.order_by(LLMCall.created_at.desc(), LLMCall.id.desc())
    return list(session.scalars(statement).all())


# LLM 输出校验调试端点（Module 17 可测路由）
@router.post("/analyzer/validate")
def validate_llm_output(
        payload: dict,
        allowed_evidence_refs: list[str] | None = None,
) -> dict:
    """LLM 分析输出校验调试端点。

    接收 LLM 原始输出 JSON 和允许的 evidence refs，
    调用 `validate_llm_analysis_output()` 返回 5 层校验结果。

    可用于在第 17 章完成后用 curl 直观看到校验器的拒绝原因。
    """
    from app.llm.analyzer import validate_llm_analysis_output

    refs = set(allowed_evidence_refs or [])
    result = validate_llm_analysis_output(payload, refs)
    return {
        "accepted": result.accepted,
        "validation": result.validation,
    }
