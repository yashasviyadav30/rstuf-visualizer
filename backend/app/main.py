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

from app.api.routes import router

# The image keeps the layout of the source tree, so the interface sits beside
# the backend in both.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(
    title="RSTUF Visualizer",
    description="Read-only view of a TUF repository managed by RSTUF.",
    version="0.1.0",
)

app.include_router(router)

# Registered last so the API and the health probe are matched first, and the
# interface only answers for paths nothing else claimed.
if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=str(FRONTEND_DIR))
