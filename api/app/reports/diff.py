import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.reports import build_analysis_package
from app.verifiers.package import as_list, latest_item, value_of

COLLECTIONS = ["findings", "risks", "questions", "recommendations"]
SNAPSHOT_COLLECTIONS = [
    "turns",
    "evidence_items",
    *COLLECTIONS,
    "quality_scores",
]

IDENTITY_FIELDS = ("title", "prompt", "summary")
# 这些字段由数据库或单次 run 生成，会随版本变化；diff 的 changed 只比较业务内容。
VOLATILE_FIELDS = {
    "id",
    "project_id",
    "run_id",
    "turn_id",
    "created_at",
    "updated_at",
    "started_at",
    "completed_at",
    "answered_at",
    "evidence_refs_json",
}


# 构建报告快照：以报告创建时间为界截断 run 产物，避免后写入数据污染历史版本
def build_report_package_snapshot(session: Session, report: Any) -> dict[str, Any]:
    package = build_analysis_package(session, value_of(report, "run"))
    cutoff = value_of(report, "created_at")
    if cutoff is None:
        return package

    snapshot = dict(package)
    for collection in SNAPSHOT_COLLECTIONS:
        snapshot[collection] = [
            item
            for item in as_list(value_of(package, collection, []))
            if created_at_before_or_equal(item, cutoff)
        ]
    return snapshot


# 对比两个集合：按身份键输出 added/removed/changed
def diff_collection(before: Any, after: Any) -> dict[str, list[dict[str, Any]]]:
    before_index = index_collection(before)
    after_index = index_collection(after)
    before_keys = set(before_index)
    after_keys = set(after_index)

    added = [after_index[key] for key in sorted(after_keys - before_keys)]
    removed = [before_index[key] for key in sorted(before_keys - after_keys)]
    changed = [
        {
            "key": key,
            "before": before_index[key],
            "after": after_index[key],
        }
        for key in sorted(before_keys & after_keys)
        if before_index[key] != after_index[key]
    ]
    return {"added": added, "removed": removed, "changed": changed}


# 对比两个报告快照：质量分变化 + 各业务集合的 diff
def diff_report_snapshots(before: Any, after: Any) -> dict[str, Any]:
    quality_before = latest_quality_score(before)
    quality_after = latest_quality_score(after)
    quality_delta = None if quality_before is None or quality_after is None else quality_after - quality_before
    diff: dict[str, Any] = {
        "quality_before": quality_before,
        "quality_after": quality_after,
        "quality_delta": quality_delta,
    }
    for collection in COLLECTIONS:
        diff[collection] = diff_collection(value_of(before, collection, []), value_of(after, collection, []))
    return diff


# 取分析包最新质量分（overall_score），无则返回 None
def latest_quality_score(package: Any) -> int | None:
    score = latest_item(value_of(package, "quality_scores", []))
    if score is None:
        return None
    value = value_of(score, "overall_score")
    return int(value) if value is not None else None


# 判断条目创建时间是否早于或等于截止时间（时间无法解析时视为通过）
def created_at_before_or_equal(item: Any, cutoff: datetime) -> bool:
    created_at = value_of(item, "created_at")
    if not isinstance(created_at, datetime):
        return True
    return comparable_datetime(created_at) <= comparable_datetime(cutoff)


# 把 datetime 统一为 UTC 以便比较
def comparable_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# 把集合按身份键建立索引，同名条目追加序号避免互相覆盖
def index_collection(items: Any) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    key_counts: dict[str, int] = {}
    for item in as_list(items):
        snapshot = snapshot_item(item)
        # 同一轮报告里理论上不应出现同名条目；这里保留序号，避免重复标题互相覆盖。
        base_key = identity_key(item, snapshot)
        key_counts[base_key] = key_counts.get(base_key, 0) + 1
        key = base_key if key_counts[base_key] == 1 else f"{base_key}#{key_counts[base_key]}"
        indexed[key] = snapshot
    return indexed


# 生成条目的身份键：title/prompt/summary 优先，其次 id，最后整条序列化
def identity_key(item: Any, snapshot: dict[str, Any]) -> str:
    for field in IDENTITY_FIELDS:
        value = snapshot.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    item_id = value_of(item, "id")
    if item_id not in (None, ""):
        return f"id:{item_id}"
    return f"item:{json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)}"


# 把条目拍平成可比较的 dict：过滤内部字段与易变字段，值统一 JSON 化
def snapshot_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        pairs = item.items()
    elif hasattr(item, "__table__"):
        pairs = ((column.name, value_of(item, column.name)) for column in item.__table__.columns)
    else:
        pairs = vars(item).items() if hasattr(item, "__dict__") else [("value", item)]

    snapshot: dict[str, Any] = {}
    for key, value in pairs:
        if key.startswith("_") or key in VOLATILE_FIELDS:
            continue
        snapshot[key] = jsonable_value(value)
    return snapshot


# 把任意值转成可 JSON 序列化的值（Decimal/日期/集合统一处理）
def jsonable_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): jsonable_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable_value(inner) for inner in value]
    return str(value)
