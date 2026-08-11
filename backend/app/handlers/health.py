# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Liveness, and nothing else.

Kept at the root rather than under the version prefix, because probes are
configured once when a deployment is created and should never have to move.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Report that the process is alive.

    Polled by the container orchestrator, not by the browser. It says
    nothing about the state of the TUF repository.
    """
    return {"status": "ok"}
