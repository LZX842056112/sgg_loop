from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import CodebaseMap, Project, Source, SourceSnapshot
from app.services.audit import record_event
from app.tools.code_scan_tools import scan_codebase
from app.tools.file_tools import read_local_file
from time import perf_counter  # ← 新增：计算工具耗时
from app.db.models import ToolCall  # ← 新增：工具调用账本


def list_inventory(session: Session, project: Project) -> dict:
    """列出项目的所有采集快照和代码库地图。"""
    snapshots = list(
        session.scalars(
            select(SourceSnapshot)
            .where(SourceSnapshot.project_id == project.id)
            .order_by(SourceSnapshot.created_at.asc(), SourceSnapshot.id.asc())
        ).all()
    )
    codebase_maps = list(
        session.scalars(
            select(CodebaseMap)
            .where(CodebaseMap.project_id == project.id)
            .order_by(CodebaseMap.created_at.asc(), CodebaseMap.id.asc())
        ).all()
    )
    return {
        "project_id": project.id,
        "snapshots": snapshots,
        "codebase_maps": codebase_maps,
    }


def collect_project_sources(
        session: Session, project: Project, settings: Settings,
        source_ids: set[str] | None = None,
) -> dict:
    """采集项目资料源——逐个扫描，按源隔离异常。"""
    statement = select(Source).where(Source.project_id == project.id)
    if source_ids is not None:
        if not source_ids:
            return list_inventory(session, project)
        statement = statement.where(Source.id.in_(source_ids))

    sources = list(
        session.scalars(
            statement.order_by(Source.created_at.asc(), Source.id.asc())
        ).all()
    )

    for source in sources:
        record_event(session, event_type="source.collection_started",
                     message="Source collection started", project_id=project.id,
                     payload={"source_id": source.id, "source_type": source.source_type})
        try:
            snapshot_data, codebase_data = _collect_one_source(session, source, project, settings)
            snapshot = SourceSnapshot(
                project_id=project.id, source_id=source.id,
                source_type=source.source_type,
                status=snapshot_data["status"],
                title=snapshot_data.get("title"),
                content_excerpt=snapshot_data.get("content_excerpt"),
                content_path=snapshot_data.get("content_path"),
                metadata_json=snapshot_data.get("metadata", {}),
                skipped_items_json=snapshot_data.get("skipped_items", []),
            )
            session.add(snapshot)
            if codebase_data is not None:
                session.add(CodebaseMap(
                    project_id=project.id, source_id=source.id,
                    root_label=codebase_data["root_label"],
                    tech_stack_json=codebase_data["tech_stack"],
                    dependency_files_json=codebase_data["dependency_files"],
                    config_files_json=codebase_data["config_files"],
                    test_files_json=codebase_data["test_files"],
                    entrypoint_files_json=codebase_data["entrypoint_files"],
                    readme_excerpt=codebase_data.get("readme_excerpt"),
                    file_tree_json=codebase_data["file_tree"],
                    skipped_items_json=codebase_data["skipped_items"],
                    metadata_json=codebase_data["metadata"],
                ))
            source.status = snapshot_data["status"]
            record_event(session, event_type="source.collected",
                         message="Source collected", project_id=project.id,
                         payload={"source_id": source.id, "status": source.status})
        except Exception as exc:
            source.status = "failed"
            session.add(SourceSnapshot(
                project_id=project.id, source_id=source.id,
                source_type=source.source_type, status="failed",
                title=source.normalized_uri, metadata_json={},
                skipped_items_json=[], error_message=str(exc),
            ))
            record_event(session, event_type="source.collection_failed",
                         message="Source collection failed", project_id=project.id,
                         payload={"source_id": source.id, "error": str(exc)})

    session.flush()
    return list_inventory(session, project)


def _record_tool_call(
        session: Session,
        project_id: str,
        tool_name: str,
        input_summary: dict,
        output_summary: dict,
        *,
        status: str = "succeeded",
        error_message: str | None = None,
        latency_ms: int | None = None,
) -> None:
    """把采集中的工具调用写入 tool_calls 账本（项目级，run 尚未创建）。"""
    session.add(
        ToolCall(
            project_id=project_id,
            run_id=None,
            tool_name=tool_name,
            permission_level="L0",
            status=status,
            input_summary_json=input_summary,
            output_summary_json=output_summary,
            error_message=error_message,
            latency_ms=latency_ms,
        )
    )
    session.flush()


def _collect_one_source(
        session: Session,
        source: Source,
        project: Project,
        settings: Settings) -> tuple[dict, dict | None]:
    """根据 source_type 分派到对应的采集器。"""
    if source.source_type == "local_file":
        return read_local_file(
            Path(source.normalized_uri),
            max_file_bytes=settings.source_max_file_bytes,
            excerpt_chars=settings.source_excerpt_chars,
        ), None

    if source.source_type == "local_directory":
        codebase_data = scan_codebase(
            Path(source.normalized_uri),
            max_file_bytes=settings.source_max_file_bytes,
            excerpt_chars=settings.source_excerpt_chars,
        )
        snapshot_data = {
            "status": "collected",
            "title": codebase_data["root_label"],
            "content_excerpt": codebase_data.get("readme_excerpt"),
            "metadata": codebase_data["metadata"],
            "skipped_items": codebase_data["skipped_items"],
        }
        return snapshot_data, codebase_data

    if source.source_type == "web_url":
        from app.tools.web_tools import fetch_web_url

        started = perf_counter()
        try:
            result = fetch_web_url(
                source.normalized_uri,
                timeout_seconds=settings.web_fetch_timeout_seconds,
                excerpt_chars=settings.source_excerpt_chars,
            )
        except Exception as exc:
            _record_tool_call(
                session, project.id, "fetch_web_url",
                {"url": source.normalized_uri},
                {"status": "failed"},
                status="failed", error_message=str(exc),
                latency_ms=int((perf_counter() - started) * 1000),
            )
            raise
        _record_tool_call(
            session, project.id, "fetch_web_url",
            {"url": source.normalized_uri},
            {"status": "succeeded", "title": result.get("title")},
            latency_ms=int((perf_counter() - started) * 1000),
        )
        return result, None

    if source.source_type == "github_repo":
        from app.tools.git_tools import clone_public_github_repo

        started = perf_counter()
        try:
            clone_data = clone_public_github_repo(
                source.normalized_uri,
                workspace_root=settings.workspace_root,
                project_id=project.id,
                timeout_seconds=settings.git_clone_timeout_seconds,
            )
        except Exception as exc:
            _record_tool_call(
                session, project.id, "clone_public_github_repo",
                {"url": source.normalized_uri, "project_id": project.id},
                {"status": "failed"},
                status="failed", error_message=str(exc),
                latency_ms=int((perf_counter() - started) * 1000),
            )
            raise
        _record_tool_call(
            session, project.id, "clone_public_github_repo",
            {"url": source.normalized_uri, "project_id": project.id},
            {"status": "succeeded", "local_path": clone_data["metadata"]["local_path"]},
            latency_ms=int((perf_counter() - started) * 1000),
        )
        codebase_data = scan_codebase(
            Path(clone_data["metadata"]["local_path"]),
            max_file_bytes=settings.source_max_file_bytes,
            excerpt_chars=settings.source_excerpt_chars,
        )
        snapshot_data = {
            **clone_data,
            "content_excerpt": codebase_data.get("readme_excerpt"),
            "metadata": {
                **clone_data["metadata"],
                "scan": codebase_data["metadata"],
            },
            "skipped_items": codebase_data["skipped_items"],
        }
        return snapshot_data, codebase_data

    # github_repo 和 web_url 在 Module 20 补全
    raise ValueError(f"Unsupported source type (coming in Module 20): {source.source_type}")
