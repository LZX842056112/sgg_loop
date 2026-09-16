from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RESEARCH_PROFILE = "quick_onboarding"

_VALID_PROFILE_KEYS = {
    "quick_onboarding",
    "architecture_understanding",
    "extension_evaluation",
    "teaching_breakdown",
    "delivery_acceptance",
}


@dataclass(frozen=True)
class ResearchProfile:
    key: str
    label: str
    description: str
    checklist: list[str]
    quality_weights: dict[str, float]
    verifier_checks: list[str]
    report_sections: list[str]
    required_evidence_types: list[str]


# ---------- 最小可用版：只有名称，完整定义在 Module 16 补全 ----------

_PROFILE_LABELS: dict[str, str] = {
    "quick_onboarding": "快速接手",
    "architecture_understanding": "架构理解",
    "extension_evaluation": "二开评估",
    "teaching_breakdown": "教学拆解",
    "delivery_acceptance": "交付验收",
}


def list_research_profiles() -> list[ResearchProfile]:
    """返回所有调研档位的简要信息。完整字段在 Module 16 补全。"""
    return [
        ResearchProfile(
            key=k,
            label=v,
            description="",
            checklist=[],
            quality_weights={},
            verifier_checks=[],
            report_sections=[],
            required_evidence_types=[],
        )
        for k, v in _PROFILE_LABELS.items()
    ]


def get_research_profile(key: str | None) -> ResearchProfile | None:
    key = key or DEFAULT_RESEARCH_PROFILE
    label = _PROFILE_LABELS.get(key)
    if label is None:
        return None
    return ResearchProfile(
        key=key,
        label=label,
        description="",
        checklist=[],
        quality_weights={},
        verifier_checks=[],
        report_sections=[],
        required_evidence_types=[],
    )


def research_profile_exists(key: str) -> bool:
    return key in _VALID_PROFILE_KEYS
