from typing import Any


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def value_of(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def verify_analysis_package(package: dict, inventory: dict) -> dict:
    """最简验证——检查必需证据类型是否齐备。Module 19 补全完整验证逻辑。"""
    checks = []
    passed = True

    evidence_count = len(as_list(package.get("evidence_items")))
    findings_count = len(as_list(package.get("findings")))
    risks_count = len(as_list(package.get("risks")))

    checks.append({
        "name": "structure_completeness",
        "passed": evidence_count > 0 and findings_count > 0,
        "severity": "error" if evidence_count == 0 else "info",
        "messages": [
            f"证据项：{evidence_count}，发现：{findings_count}，风险：{risks_count}"
        ],
    })

    if evidence_count == 0:
        passed = False

    return {
        "passed": passed,
        "risk_level": "high" if risks_count > 0 else "low",
        "summary": f"证据 {evidence_count} 项，发现 {findings_count} 条，风险 {risks_count} 条",
        "checks": checks,
    }
