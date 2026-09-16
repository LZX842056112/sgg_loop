import os
from time import perf_counter

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import LLMProfile
from app.llm.ledger import record_llm_call
from app.llm.openai_compatible import OpenAICompatibleClient
from app.llm.profiles import (
    default_profile_from_settings,
    get_enabled_profile,
    profile_is_configured,
)

UNCONFIGURED_ERROR = "LLM profile is not configured"


class LLMRouter:
    """LLM 调用统一入口——最小版：无预算控制，Module 23 补全 budget + 完整 ledger。"""

    def __init__(self, session: Session, transport: httpx.BaseTransport | None = None) -> None:
        self.session = session
        self.transport = transport

    def profile_for(self, task_type: str) -> LLMProfile | None:
        """获取任务类型对应的最佳 profile：DB profile 优先，回退到 .env。"""
        db_profile = get_enabled_profile(self.session, task_type)
        if db_profile is not None:
            return db_profile
        return default_profile_from_settings(get_settings(), task_type)

    def _resolve_api_key(self, profile: LLMProfile | None) -> str | None:
        if profile is None or not profile.api_key_env_name:
            return None
        return os.getenv(profile.api_key_env_name)

    def chat(
            self,
            *,
            task_type: str,
            messages: list[dict],
            project_id: str | None = None,
            run_id: str | None = None,
            profile_id: str | None = None,
            required: bool = False,
    ) -> dict:
        """发起一次 LLM 调用——自动选择 profile，记录调用日志。"""

        # 1. 确定使用哪个 profile
        if profile_id is not None:
            profile = self.session.get(LLMProfile, profile_id)
        else:
            profile = self.profile_for(task_type)

        api_key = self._resolve_api_key(profile)

        # 2. 检查是否可调用
        if profile is None or not profile_is_configured(profile, api_key=api_key):
            call = record_llm_call(
                self.session,
                project_id=project_id, run_id=run_id,
                profile_id=profile.id if profile else None,
                task_type=task_type,
                provider=profile.provider if profile else "",
                model=profile.model if profile else "",
                messages=messages,
                usage={}, latency_ms=None,
                status="skipped",
                error_message=UNCONFIGURED_ERROR,
            )
            if required:
                self.session.commit()
                raise ValueError(UNCONFIGURED_ERROR)
            return {
                "status": "skipped", "call_id": call.id,
                "text": "", "usage": {},
                "error_message": UNCONFIGURED_ERROR,
            }

        # 3. 创建客户端并发起调用
        client = OpenAICompatibleClient(
            provider=profile.provider,
            api_key=api_key,
            base_url=profile.base_url,
            model=profile.model,
            api_key_required=bool(profile.api_key_required),
            timeout_seconds=profile.timeout_seconds,
            transport=self.transport,
        )

        started = perf_counter()
        try:
            result = client.chat(
                messages=messages,
                max_tokens=profile.max_tokens,
                temperature=profile.temperature,
            )
        except Exception as exc:
            latency_ms = int((perf_counter() - started) * 1000)
            call = record_llm_call(
                self.session,
                project_id=project_id, run_id=run_id,
                profile_id=profile.id, task_type=task_type,
                provider=profile.provider, model=profile.model,
                messages=messages,
                usage={}, latency_ms=latency_ms,
                status="failed", error_message=str(exc),
            )
            if required:
                self.session.commit()
                raise
            return {
                "status": "failed", "call_id": call.id,
                "text": "", "usage": {},
                "error_message": str(exc),
            }

        # 4. 记录成功调用
        latency_ms = int((perf_counter() - started) * 1000)
        call = record_llm_call(
            self.session,
            project_id=project_id, run_id=run_id,
            profile_id=profile.id, task_type=task_type,
            provider=profile.provider, model=profile.model,
            messages=messages,
            usage=result.get("usage", {}), latency_ms=latency_ms,
            status="succeeded",
        )
        return {
            "status": "succeeded", "call_id": call.id,
            "text": result.get("text", ""),
            "usage": result.get("usage", {}),
        }
