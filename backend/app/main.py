# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Application entry point.

Builds the FastAPI application, attaches the API routes, and serves the
interface from the same process. One origin means the browser needs no
cross-site arrangement to reach the API, and one image means an operator
deploys one thing rather than two.

Run it with::

    uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import cors_origins

# The image keeps the layout of the source tree, so the interface sits beside
# the backend in both.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def create_app() -> FastAPI:
    """Assemble the application.

    A function rather than a bare module body, so a test can build one under
    different configuration instead of reloading this module and leaving two
    applications behind.
    """
    application = FastAPI(
        title="RSTUF Visualizer",
        description="Read-only view of a TUF repository managed by RSTUF.",
        version="0.1.0",
    )

    application.include_router(router)

    # Named origins only, and only where a deployment asks for them. Nothing
    # here is needed by the shipped arrangement, where the interface is served
    # from this same process; a frontend development server answers on a port
    # of its own, which makes it another origin.
    #
    # Credentials are not allowed across origins. Every route is a GET and
    # none of them reads a cookie, and it is that pairing — a permitted origin
    # plus credentials — that would let another site act as a visitor.
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
