# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Application entry point.

Builds the FastAPI application and attaches the API routes. Run it with::

    uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="RSTUF Visualizer",
    description="Read-only view of a TUF repository managed by RSTUF.",
    version="0.1.0",
)

app.include_router(router)
