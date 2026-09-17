from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Project, Source
from app.services.audit import record_event
from app.services.collection import collect_project_sources


def create_code_analysis_demo_project(
        session: Session, settings: Settings,
) -> Project:
    """创建一个完整的演示项目：项目 + 示例源 + 采集。"""
    project = Project(
        name="Demo - 代码分析示例",
        topic="快速体验 Loop Engineering 全流程",
        analysis_goal="验证从项目创建到报告生成的全链路",
        research_profile="quick_onboarding",
        max_turns=4,
    )
    session.add(project)
    session.flush()

    # 创建一个示例源（指向本项目自身，作为演示）
    source = Source(
        project_id=project.id,
        source_type="local_directory",
        uri="Demo 示例源",
        normalized_uri=str(settings.workspace_root.parent),
        status="pending",
        metadata_json={"demo": True},
    )
    session.add(source)

    record_event(session, event_type="project.created",
                 message="Demo project created", project_id=project.id,
                 payload={"name": project.name})

    record_event(session, event_type="source.created",
                 message="Demo source created", project_id=project.id,
                 payload={"source_id": source.id})

    session.flush()

    # 尝试采集（可能会因路径不存在而失败，不影响流程展示）
    try:
        collect_project_sources(session, project, settings)
    except Exception:
        pass

    return project
