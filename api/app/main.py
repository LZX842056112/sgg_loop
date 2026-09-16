from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routers_projects, routers_research_profiles
from app.api import routers_sources, routers_source_bundles, routers_inventory
from app.api import routers_events
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routers_projects.router)
    app.include_router(routers_research_profiles.router)
    app.include_router(routers_sources.router)
    app.include_router(routers_source_bundles.router)
    app.include_router(routers_inventory.router)
    app.include_router(routers_events.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
