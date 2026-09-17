from copy import deepcopy
from typing import Any

MERGE_KEYS = ["evidence", "findings", "risks", "questions", "recommendations"]


# 把 LLM 增强产物合并进确定性分析：只追加不覆盖，并为每条 LLM 条目打上 source=llm_analyzer 标记
def merge_llm_analysis(analysis: dict[str, Any], llm_payload: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(analysis)

    for key in MERGE_KEYS:
        merged.setdefault(key, [])
        items = llm_payload.get(key, [])
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                raise ValueError("LLM analysis item must be an object")

            appended = deepcopy(item)
            metadata = appended.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["source"] = "llm_analyzer"
            appended["metadata"] = metadata
            merged[key].append(appended)

    return merged
