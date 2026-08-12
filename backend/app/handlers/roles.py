# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""One role at a time, and the bytes it was verified from."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from app.client.tuf_client import MetadataUnavailableError
from app.dto.schemas import RoleDetailResponse
from app.handlers import errors
from app.handlers.validation import ROLE_NAME
from app.services.metadata_service import (
    MetadataService,
    TrustAnchorMissingError,
    UnknownRoleError,
    get_metadata_service,
)

router = APIRouter(prefix="/api/v1", tags=["metadata"])


@router.get(
    "/roles/{role}",
    response_model=RoleDetailResponse,
    responses=errors.ROLE,
)
async def role_detail(
    role: str = Path(pattern=ROLE_NAME, description="Role name"),
    service: MetadataService = Depends(get_metadata_service),
) -> RoleDetailResponse:
    """Open one role.

    Top-level roles were verified during the refresh. A delegated role is
    fetched now and checked by its parent, which is what makes opening one
    cost a single request instead of every bin costing one up front.
    """
    try:
        return await service.role(role)
    except (UnknownRoleError, StopIteration) as exc:
        detail = str(exc) or role
        if detail == role:
            detail = f"No such role: {role}"
        raise HTTPException(status_code=404, detail=detail) from exc
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get(
    "/roles/{role}/raw",
    response_class=Response,
    responses=errors.ROLE,
)
async def role_raw(
    role: str = Path(pattern=ROLE_NAME, description="Role name"),
    service: MetadataService = Depends(get_metadata_service),
) -> Response:
    """Serve the bytes one role was verified from.

    Sent as a download, never as HTML a browser will render, so a
    repository cannot put script into a file this service hands to a browser.
    """
    try:
        document = await service.raw_metadata(role)
    except (UnknownRoleError, StopIteration) as exc:
        detail = str(exc) or f"No such role: {role}"
        raise HTTPException(status_code=404, detail=detail) from exc
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(
        content=document,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{role}.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )
