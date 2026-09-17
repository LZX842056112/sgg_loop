import json
from typing import Any


# 去掉 LLM 输出外层的 markdown 代码围栏（``` 包裹）
def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


# 从 LLM 输出文本中提取第一个合法的 JSON 对象（raw_decode 容忍尾部解释文字）
def extract_json_object(text: str) -> dict[str, Any]:
    normalized = _strip_markdown_fence(text)
    decoder = json.JSONDecoder()
    for index, char in enumerate(normalized):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(normalized[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("LLM response does not contain a JSON object")
