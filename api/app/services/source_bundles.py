from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import SourceValidationError, validate_source_input
from app.db.models import Project, Source, SourceBundle, SourceBundleItem
from app.schemas.source_bundle import SourceBundleCreate, SourceBundleItemCreate
from app.services.audit import record_event

# input_type → source_type 映射
SOURCE_BUNDLE_INPUT_TYPES = {
    "github_repo": "github_repo",
    "local_directory": "local_directory",
    "local_file": "local_file",
    "web_page": "web_url",
    "markdown_file": "local_file",
    "pdf_file": "local_file",
}
COLLECTION_SUCCESS_STATUSES = {"collected", "skipped"}
COLLECTION_TERMINAL_STATUSES = COLLECTION_SUCCESS_STATUSES | {"failed"}


def create_source_bundle(
        session: Session, project: Project, payload: SourceBundleCreate,
) -> SourceBundle:
    """创建资料包：校验每个条目 → 创建 Source → 创建 BundleItem。"""
    bundle = SourceBundle(
        project_id=project.id, name=payload.name,
        status="pending", metadata_json={},
    )
    session.add(bundle)
    session.flush()

    source_count = 0
    failed_count = 0
    item_summaries: list[dict] = []

    for item_payload in payload.items:
        item, source_created = _build_bundle_item(session, project, bundle, item_payload)
        session.add(item)
        session.flush()
        if source_created:
            source_count += 1
        else:
            failed_count += 1
        item_summaries.append({
            "input_type": item.input_type, "status": item.status,
            "source_id": item.source_id, "normalized_uri": item.normalized_uri,
            "error_message": item.error_message,
        })

    bundle.status = _resolve_bundle_status(len(payload.items), source_count)
    bundle.metadata_json = {
        "item_count": len(payload.items),
        "source_count": source_count,
        "failed_count": failed_count,
    }
    session.flush()
    record_event(session, event_type="source_bundle.created",
                 message="Source bundle created", project_id=project.id,
                 payload={"bundle_id": bundle.id, "status": bundle.status,
                          "item_count": len(payload.items), "source_count": source_count,
                          "failed_count": failed_count, "items": item_summaries})
    return bundle


def _build_bundle_item(
        session: Session, project: Project, bundle: SourceBundle,
        item_payload: SourceBundleItemCreate,
) -> tuple[SourceBundleItem, bool]:
    """校验单个条目，成功则创建 Source，失败则记录错误状态。"""
    input_type = item_payload.input_type
    source_type = SOURCE_BUNDLE_INPUT_TYPES.get(input_type, input_type)
    base_metadata = {"input_type": input_type, "source_type": source_type}

    try:
        validated = validate_source_input(source_type, item_payload.raw_value)
    except SourceValidationError as exc:
        return (
            SourceBundleItem(
                bundle_id=bundle.id, project_id=project.id,
                input_type=input_type, raw_value=item_payload.raw_value,
                status="failed", error_message=str(exc),
                metadata_json=base_metadata,
            ),
            False,
        )

    source = Source(
        project_id=project.id, source_type=source_type,
        uri=item_payload.raw_value, normalized_uri=validated.normalized_uri,
        status="pending", metadata_json={**base_metadata, **validated.metadata},
    )
    session.add(source)
    return (
        SourceBundleItem(
            bundle_id=bundle.id, project_id=project.id,
            source=source, input_type=input_type,
            raw_value=item_payload.raw_value,
            normalized_uri=validated.normalized_uri,
            status="pending", metadata_json={**base_metadata, **validated.metadata},
        ),
        True,
    )


def _resolve_bundle_status(item_count: int, source_count: int) -> str:
    if source_count == item_count:
        return "ready"
    if source_count == 0:
        return "failed"
    return "partial"


def list_source_bundles(session: Session, project: Project) -> list[SourceBundle]:
    statement = (
        select(SourceBundle)
        .options(selectinload(SourceBundle.items))
        .where(SourceBundle.project_id == project.id)
        .order_by(SourceBundle.created_at.asc(), SourceBundle.id.asc())
    )
    return list(session.scalars(statement).all())


def get_source_bundle(session: Session, project: Project, bundle_id: str) -> SourceBundle | None:
    statement = (
        select(SourceBundle)
        .options(selectinload(SourceBundle.items))
        .where(SourceBundle.id == bundle_id, SourceBundle.project_id == project.id)
    )
    return session.scalar(statement)


def get_source_bundle_for_collection(
        session: Session, project: Project, bundle_id: str,
) -> SourceBundle | None:
    """加载资料包及其条目的关联 Source，用于采集操作。"""
    statement = (
        select(SourceBundle)
        .options(selectinload(SourceBundle.items).selectinload(SourceBundleItem.source))
        .where(SourceBundle.id == bundle_id, SourceBundle.project_id == project.id)
    )
    return session.scalar(statement)


def collectable_source_ids(bundle: SourceBundle) -> set[str]:
    """只采集尚未进入终态的源。"""
    return {
        item.source_id
        for item in bundle.items
        if item.source_id is not None
           and item.source is not None
           and item.source.status not in COLLECTION_TERMINAL_STATUSES
    }


def refresh_bundle_item_collection_state(session: Session, bundle: SourceBundle) -> SourceBundle:
    """采集完成后，把 Source 的状态同步到 BundleItem。"""
    for item in bundle.items:
        if item.source is not None and item.source.status in COLLECTION_TERMINAL_STATUSES:
            item.status = item.source.status

    # 只统计真正挂载了 source 的条目,未挂载 source 的 pending 条目不参与判定
    item_statuses = [item.status for item in bundle.items if item.source is not None]
    if not item_statuses:
        # 没有可判定条目时保持原状态,不误判为 collected
        pass
    elif all(s in COLLECTION_SUCCESS_STATUSES for s in item_statuses):
        bundle.status = "collected"
    elif all(s == "failed" for s in item_statuses):
        bundle.status = "failed"
    else:
        # 成功与失败混合,不能过滤掉 failed 后误判为全成功
        bundle.status = "partial"

    session.flush()
    return bundle
