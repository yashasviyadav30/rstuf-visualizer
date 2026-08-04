# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""HTTP endpoints exposed to the browser.

Every route here is a GET. The visualizer reads a TUF repository and changes
nothing in it.

Answers follow one rule. Broken trust is the subject of this service, so an
expired or badly signed repository is a normal answer carrying a status. A
request for something that does not exist is the caller's mistake. Only a
repository that cannot be reached, or one that cannot be checked at all, is
reported as a failure of the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.models.schemas import (
    ArtifactsResponse,
    OverviewResponse,
    RoleDetailResponse,
    RootsResponse,
    StatusResponse,
)
from app.service import (
    TrustAnchorMissingError,
    UnknownRoleError,
    VisualizerService,
    get_service,
)
from app.tuf.roots import DEFAULT_HISTORY, MAX_HISTORY
from app.tuf.trust import MetadataUnavailableError

router = APIRouter()
v1 = APIRouter(prefix="/api/v1", tags=["metadata"])

# A role name reaches us in a URL and is used to build a filename, so it is
# constrained here rather than trusted. This also rejects path traversal
# before any of our own code runs.
ROLE_NAME = r"^[A-Za-z0-9._-]{1,128}$"


@router.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Report that the process is alive.

    Polled by the container orchestrator, not by the browser. It says
    nothing about the state of the TUF repository.
    """
    return {"status": "ok"}


@v1.get("/overview", response_model=OverviewResponse)
async def overview(
    refresh: bool = Query(
        default=False,
        description="Discard the cached result and check the repository now",
    ),
    service: VisualizerService = Depends(get_service),
) -> OverviewResponse:
    """Describe the repository: its roles, their state, and the tree."""
    try:
        return await service.overview(refresh=refresh)
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@v1.get("/roles/{role}", response_model=RoleDetailResponse)
async def role_detail(
    role: str = Path(pattern=ROLE_NAME, description="Role name"),
    service: VisualizerService = Depends(get_service),
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


@v1.get("/roles/{role}/raw", response_class=Response)
async def role_raw(
    role: str = Path(pattern=ROLE_NAME, description="Role name"),
    service: VisualizerService = Depends(get_service),
) -> Response:
    """Serve the bytes one role was verified from.

    Sent as a download rather than rendered, and never as HTML, so a
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


@v1.get("/roots", response_model=RootsResponse)
async def roots(
    limit: int = Query(
        default=DEFAULT_HISTORY,
        ge=1,
        le=MAX_HISTORY,
        description="How many versions back to walk, newest first",
    ),
    service: VisualizerService = Depends(get_service),
) -> RootsResponse:
    """Show how root reached its current version.

    Each step is checked against the rule the specification sets for a
    rotation, so a version that cannot be tied to the one before it is
    reported as exactly that rather than shown as settled history.
    """
    try:
        return await service.roots(limit=limit)
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@v1.get("/artifacts", response_model=ArtifactsResponse)
async def artifacts(
    search: str = Query(default="", max_length=256),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    service: VisualizerService = Depends(get_service),
) -> ArtifactsResponse:
    """List the artifacts the repository vouches for.

    Names, sizes and hashes only. The visualizer never serves the files
    themselves, and never claims one is safe to install.
    """
    try:
        return await service.artifacts(
            search=search, page=page, page_size=page_size
        )
    except TrustAnchorMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MetadataUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@v1.get("/status", response_model=StatusResponse)
async def status(
    service: VisualizerService = Depends(get_service),
) -> StatusResponse:
    """Report what the RSTUF API says, and say so when it says nothing.

    This never fails the request. Status is helpful, not load-bearing, so an
    unreachable API hides one panel and leaves the rest of the page standing.
    """
    return await service.status()


router.include_router(v1)
