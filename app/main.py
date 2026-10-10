"""Application assembly: settings, database, middleware, error handling and routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import __version__
from app.api import files, health
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware, UploadSizeLimitMiddleware
from app.core.config import Settings
from app.core.logging import configure_logging
from app.readers.registry import build_readers
from app.repositories.database import create_engine_for, prepare_database
from app.repositories.file_repository import FileRepository

DESCRIPTION = """
Upload a **KML** file or a **zipped Shapefile** and get the area of its polygons and the
length of its lines, in metres.

Coordinates in degrees are never measured directly. Each feature is projected to the
WGS 84 / UTM zone it lies in, and the response names the EPSG code used.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine_for(settings.database_url)
    # expire_on_commit=False: a record stays readable after its transaction ends, which is
    # when the response is built from it.
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        prepare_database(engine)
        with session_factory() as session:
            FileRepository(session).fail_interrupted()
        yield
        engine.dispose()

    app = FastAPI(
        title="Geospatial File Measurement API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        # The routes answer with and without a trailing slash themselves; see app/api/files.py.
        redirect_slashes=False,
    )
    app.state.session_factory = session_factory
    app.state.readers = build_readers(settings)

    # Added last means outermost: the request id exists before anything else runs.
    app.add_middleware(UploadSizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(files.router)
    app.include_router(health.router)
    return app


app = create_app()
