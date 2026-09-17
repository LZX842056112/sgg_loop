from copy import deepcopy
from dataclasses import dataclass
from typing import Any

REQUIRED_COLLECTION_KEYS = ["evidence", "findings", "risks", "questions", "recommendations"]


# 校验结果的数据结构：accepted 是否通过、content 规范化后的内容、validation 校验明细
@dataclass
class LLMAnalysisValidation:
    accepted: bool
    content: dict[str, Any]
    validation: dict[str, Any]


# 规范化某个集合字段：缺省/非列表时记错误并返回空列表，合法则深拷贝返回
def _normalize_collection(
        payload: dict[str, Any],
        key: str,
        messages: list[str],
        *,
        required: bool = False,
) -> list[Any]:
    if key not in payload:
        if required:
            messages.append(f"{key} is required")
        return []
    value = payload[key]
    if not isinstance(value, list):
        messages.append(f"{key} must be a list")
        return []
    return deepcopy(value)


# 提取并清洗 LLM 输出的 reasoning_summary 文本
def _reasoning_summary(payload: dict[str, Any]) -> str:
    value = payload.get("reasoning_summary", "")
    if not isinstance(value, str):
        return ""
    return value.strip()


# 生成校验错误信息前缀，如 findings[2].title
def _message_prefix(key: str, index: int, field: str) -> str:
    return f"{key}[{index}].{field}"


# 判断值是否为非空字符串
def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


# 校验必填字符串字段，为空或类型不对则追加错误
def _validate_required_string(
        item: dict[str, Any], key: str, index: int, field: str, messages: list[str]
) -> None:
    if not _is_non_empty_string(item.get(field)):
        messages.append(f"{_message_prefix(key, index, field)} must be a non-empty string")


# 校验可选字符串字段：字段存在但类型不对时追加错误
def _validate_optional_string(
        item: dict[str, Any], key: str, index: int, field: str, messages: list[str]
) -> None:
    if field in item and not isinstance(item[field], str):
        messages.append(f"{_message_prefix(key, index, field)} must be a string")


# 校验可选 confidence 字段：须为 0-100 的数字（排除布尔值）
def _validate_optional_confidence(
        item: dict[str, Any], key: str, index: int, messages: list[str]
) -> None:
    if "confidence" not in item:
        return
    value = item["confidence"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
        messages.append(f"{_message_prefix(key, index, 'confidence')} must be between 0 and 100")


# 校验可选 metadata 字段：缺省时补空字典，非对象则追加错误
def _validate_optional_metadata(
        item: dict[str, Any], key: str, index: int, messages: list[str]
) -> None:
    if "metadata" not in item:
        item["metadata"] = {}
        return
    if not isinstance(item["metadata"], dict):
        messages.append(f"{_message_prefix(key, index, 'metadata')} must be an object")


# 校验 evidence_refs：必须是非空字符串列表，且每条引用必须出现在允许的证据引用集合中
def _validate_evidence_refs(
        item: dict[str, Any],
        key: str,
        index: int,
        allowed_evidence_refs: set[str],
        messages: list[str],
) -> None:
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or len(refs) == 0:
        messages.append(f"{_message_prefix(key, index, 'evidence_refs')} must be a non-empty list")
        item["evidence_refs"] = []
        return
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            messages.append(f"{_message_prefix(key, index, 'evidence_refs')} must be a non-empty list of strings")
            continue
        if ref not in allowed_evidence_refs:
            messages.append(f"Unknown evidence ref: {ref}")


# 过滤出集合中的字典条目，非对象条目记错误；返回 (索引, 对象) 列表
def _validate_items_are_objects(
        content: dict[str, Any], key: str, messages: list[str]
) -> list[tuple[int, dict[str, Any]]]:
    objects: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(content[key]):
        if not isinstance(item, dict):
            messages.append(f"{key}[{index}] must be an object")
            continue
        objects.append((index, item))
    return objects


# 校验 evidence 条目的 client_ref：不能与现有引用冲突、须以 llm: 开头、不能重复
def _validate_evidence_client_ref(
        item: dict[str, Any],
        index: int,
        allowed_evidence_refs: set[str],
        seen_client_refs: set[str],
        messages: list[str],
) -> str | None:
    client_ref = item.get("client_ref")
    if not _is_non_empty_string(client_ref):
        return None
    valid = True
    if client_ref in allowed_evidence_refs:
        messages.append(f"evidence[{index}].client_ref conflicts with existing evidence ref: {client_ref}")
        valid = False
    if not client_ref.startswith("llm:"):
        messages.append(f"evidence[{index}].client_ref must start with llm:")
        valid = False
    if client_ref in seen_client_refs:
        messages.append(f"Duplicate evidence client_ref: {client_ref}")
        valid = False
    seen_client_refs.add(client_ref)
    if valid:
        return client_ref
    return None


# 校验 evidence 集合整体，返回 LLM 新增的合法 evidence client_ref 集合
def _validate_evidence_items(
        content: dict[str, Any], allowed_evidence_refs: set[str], messages: list[str]
) -> set[str]:
    seen_client_refs: set[str] = set()
    payload_llm_evidence_refs: set[str] = set()
    for index, item in _validate_items_are_objects(content, "evidence", messages):
        for field in ["client_ref", "title", "summary", "evidence_type"]:
            _validate_required_string(item, "evidence", index, field, messages)
        payload_ref = _validate_evidence_client_ref(item, index, allowed_evidence_refs, seen_client_refs, messages)
        if payload_ref is not None:
            payload_llm_evidence_refs.add(payload_ref)
        _validate_optional_confidence(item, "evidence", index, messages)
        _validate_optional_metadata(item, "evidence", index, messages)
    return payload_llm_evidence_refs


# 校验 findings 集合：必填字段 + 证据引用 + 置信度 + metadata
def _validate_finding_items(
        content: dict[str, Any], allowed_evidence_refs: set[str], messages: list[str]
) -> None:
    for index, item in _validate_items_are_objects(content, "findings", messages):
        for field in ["title", "summary", "category", "impact_level"]:
            _validate_required_string(item, "findings", index, field, messages)
        _validate_optional_confidence(item, "findings", index, messages)
        _validate_evidence_refs(item, "findings", index, allowed_evidence_refs, messages)
        _validate_optional_metadata(item, "findings", index, messages)


# 校验 risks 集合：必填字段 + 证据引用 + metadata
def _validate_risk_items(
        content: dict[str, Any], allowed_evidence_refs: set[str], messages: list[str]
) -> None:
    for index, item in _validate_items_are_objects(content, "risks", messages):
        for field in ["title", "summary", "severity", "mitigation"]:
            _validate_required_string(item, "risks", index, field, messages)
        _validate_evidence_refs(item, "risks", index, allowed_evidence_refs, messages)
        _validate_optional_metadata(item, "risks", index, messages)


# 校验 questions 集合：prompt/reason/impact 必填，status 可选
def _validate_question_items(content: dict[str, Any], messages: list[str]) -> None:
    for index, item in _validate_items_are_objects(content, "questions", messages):
        for field in ["prompt", "reason", "impact"]:
            _validate_required_string(item, "questions", index, field, messages)
        _validate_optional_string(item, "questions", index, "status", messages)
        _validate_optional_metadata(item, "questions", index, messages)


# 校验 recommendations 集合：summary/rationale 必填，next_steps 须为字符串列表
def _validate_recommendation_items(content: dict[str, Any], messages: list[str]) -> None:
    for index, item in _validate_items_are_objects(content, "recommendations", messages):
        for field in ["summary", "rationale"]:
            _validate_required_string(item, "recommendations", index, field, messages)
        _validate_optional_confidence(item, "recommendations", index, messages)
        if "next_steps" in item and (
                not isinstance(item["next_steps"], list)
                or any(not isinstance(step, str) for step in item["next_steps"])
        ):
            messages.append(f"{_message_prefix('recommendations', index, 'next_steps')} must be a list of strings")
        _validate_optional_metadata(item, "recommendations", index, messages)


# 5 层校验入口：规范化 5 类集合 + reasoning_summary/coverage_notes，逐项校验并汇总结果
def validate_llm_analysis_output(
        payload: dict[str, Any], allowed_evidence_refs: set[str]
) -> LLMAnalysisValidation:
    messages: list[str] = []
    content: dict[str, Any] = {}
    for key in REQUIRED_COLLECTION_KEYS:
        content[key] = _normalize_collection(payload, key, messages, required=True)
    content["reasoning_summary"] = _reasoning_summary(payload)
    content["coverage_notes"] = _normalize_collection(payload, "coverage_notes", messages)
    payload_llm_evidence_refs = _validate_evidence_items(content, allowed_evidence_refs, messages)
    merged_allowed_refs = allowed_evidence_refs | payload_llm_evidence_refs
    _validate_finding_items(content, merged_allowed_refs, messages)
    _validate_risk_items(content, merged_allowed_refs, messages)
    _validate_question_items(content, messages)
    _validate_recommendation_items(content, messages)
    validation = {"passed": not messages, "messages": messages}
    return LLMAnalysisValidation(accepted=validation["passed"], content=content, validation=validation)
