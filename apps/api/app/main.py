import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ai,
    assessments,
    calendar,
    health,
    materials,
    modules,
    planning,
    push,
    search,
    sessions,
    tasks,
    topic_maps,
    topics,
    tutor,
)
from app.api.errors import add_error_handlers
from app.core.config import get_settings
from app.services.search.embedding import get_embedder

log = logging.getLogger("studysensei.api")


def _log_failure(task: "asyncio.Task[object]") -> None:
    if not task.cancelled() and task.exception() is not None:
        # Not fatal: the first search tries again (and says so if it fails too).
        log.error("Loading the embedding model at startup failed", exc_info=task.exception())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the embedding model as the API starts, so the first question after a start is
    as fast as the rest (it cost about 1.4 s on first use). It loads in a thread while the
    API already answers (/health included); a search that arrives first waits for it."""
    if get_settings().preload_embedder:
        loading = asyncio.create_task(asyncio.to_thread(get_embedder))
        loading.add_done_callback(_log_failure)
        app.state.embedder_loading = loading
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="StudySensei API", version="0.1.0", lifespan=lifespan)
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
    app.include_router(topic_maps.router)
    app.include_router(assessments.router)
    app.include_router(tasks.router)
    app.include_router(sessions.router)
    app.include_router(materials.router)
    app.include_router(search.router)
    app.include_router(tutor.router)
    app.include_router(planning.router)
    app.include_router(push.router)
    app.include_router(calendar.router)
    app.include_router(ai.router)
    return app


app = create_app()
