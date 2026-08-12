# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Application entry point.

Builds the FastAPI application, attaches the API routes, and serves the
interface from the same process. One origin means the browser needs no
cross-site arrangement to reach the API, and one image means an operator
deploys one thing.

Run it with::

    uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origins, get_settings
from app.handlers import artifacts, health, overview, roles, roots, status
from app.middleware.logging import RequestLogMiddleware

# What `npm run build` produces. The image keeps the layout of the source
# tree, so this is one path in a checkout and in the container. Absent, the
# API still answers and the interface is not there, which is what running the
# backend alone looks like.
FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Read the settings before the first request arrives.

    A missing or malformed value raises here, and a server whose startup
    raised exits instead of serving. Left until the first request, the same
    mistake would pass every health check and fail every real request, which
    reads as a broken repository and not a broken deployment.
    """
    get_settings()
    yield


def create_app() -> FastAPI:
    """Assemble the application.

    A function, not a bare module body, so a test can build one under
    different configuration instead of reloading this module and leaving two
    applications behind.
    """
    application = FastAPI(
        title="RSTUF Visualizer",
        description="Read-only view of a TUF repository managed by RSTUF.",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(RequestLogMiddleware)

    # Health first, because a probe must be answerable whatever else is
    # wrong. The rest are grouped by subject and all sit under /api/v1.
    application.include_router(health.router)
    application.include_router(overview.router)
    application.include_router(roles.router)
    application.include_router(roots.router)
    application.include_router(artifacts.router)
    application.include_router(status.router)

    # Named origins only, and only where a deployment asks for them. The
    # shipped arrangement needs none: the interface is served from this same
    # process. A frontend development server answers on a port of its own,
    # which makes it another origin.
    #
    # No credentials across origins. It is that pairing, a permitted origin
    # plus credentials, that would let another site act as a visitor.
    origins = cors_origins()
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    # Registered last so the API and the health probe are matched first, and
    # the interface only answers for paths nothing else claimed.
    if FRONTEND_DIR.is_dir():
        application.frontend("/", directory=str(FRONTEND_DIR))

    return application


app = create_app()
