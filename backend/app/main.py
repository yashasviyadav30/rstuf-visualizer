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

import os
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router


def _frontend_dir() -> Path | None:
    """Decide where the interface's files live, if they are served at all.

    Unset means the copy beside the backend, which is the layout of both the
    source tree and the image. Set but empty means serve nothing, for a
    deployment putting its own front end in front of the API.

    Read from the environment rather than through Settings because it
    describes how files were laid out, not which repository to read, and
    because this module must still import when no repository is configured.
    """
    configured = os.environ.get("RSTUF_FRONTEND_DIR")
    if configured is None:
        return Path(__file__).resolve().parent.parent.parent / "frontend"
    return Path(configured) if configured else None


FRONTEND_DIR = _frontend_dir()

app = FastAPI(
    title="RSTUF Visualizer",
    description="Read-only view of a TUF repository managed by RSTUF.",
    version="0.1.0",
)

app.include_router(router)

# Registered last so the API and the health probe are matched first, and the
# interface only answers for paths nothing else claimed.
if FRONTEND_DIR is not None and FRONTEND_DIR.is_dir():
    app.frontend("/", directory=str(FRONTEND_DIR))
