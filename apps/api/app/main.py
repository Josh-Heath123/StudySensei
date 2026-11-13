from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assessments, health, materials, modules, sessions, tasks, topics
from app.api.errors import add_error_handlers
from app.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="StudySensei API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    add_error_handlers(app)
    app.include_router(health.router)
    app.include_router(modules.router)
    app.include_router(topics.router)
    app.include_router(assessments.router)
    app.include_router(tasks.router)
    app.include_router(sessions.router)
    app.include_router(materials.router)
    return app


app = create_app()
