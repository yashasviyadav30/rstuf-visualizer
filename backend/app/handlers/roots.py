# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""How root reached the version in force today."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.client.tuf_client import MetadataUnavailableError
from app.dto.schemas import RootsResponse
from app.handlers import errors
from app.repositories.root_repository import DEFAULT_HISTORY, MAX_HISTORY
from app.services.metadata_service import (
    MetadataService,
    TrustAnchorMissingError,
    get_metadata_service,
)

router = APIRouter(prefix="/api/v1", tags=["metadata"])


@router.get(
    "/roots",
    response_model=RootsResponse,
    responses=errors.REPOSITORY,
)
async def roots(
    limit: int = Query(
        default=DEFAULT_HISTORY,
        ge=1,
        le=MAX_HISTORY,
        description="How many versions back to walk, newest first",
    ),
    service: MetadataService = Depends(get_metadata_service),
) -> RootsResponse:
    """Show how root reached its current version.

    Each step is checked against the rule the specification sets for a
    rotation, so a version that cannot be tied to the one before it is
    reported as exactly that. Settled history it is not.
    """
    try:
        return await service.roots(limit=limit)
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
