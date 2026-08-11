# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What the RSTUF API reports, when one is configured."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dto.schemas import StatusResponse
from app.services.metadata_service import MetadataService, get_metadata_service

router = APIRouter(prefix="/api/v1", tags=["metadata"])


@router.get("/status", response_model=StatusResponse)
async def status(
    service: MetadataService = Depends(get_metadata_service),
) -> StatusResponse:
    """Report what the RSTUF API says, and say so when it says nothing.

    This never fails the request. Status is helpful, not load-bearing, so an
    unreachable API hides one panel and leaves the rest of the page standing.
    """
    return await service.status()
