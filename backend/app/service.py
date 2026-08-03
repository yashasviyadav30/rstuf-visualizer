# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What the endpoints call.

Holds the pieces a request needs — settings, the cache, the trust directory,
and the RSTUF API client — so the routes stay thin and the ordering rules
live in one place.
"""

from __future__ import annotations

import logging
import tempfile
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from app.cache import TTLCache
from app.config import Settings, get_settings
from app.models.schemas import (
    ArtifactsResponse,
    ArtifactSummary,
    OverviewResponse,
    RepositoryState,
    RoleDetailResponse,
    RootsResponse,
    StatusResponse,
)
from app.rstuf.client import RstufClient
from app.tuf import read
from app.tuf.roots import DEFAULT_HISTORY, RootHistory, load_root_history
from app.tuf.trust import (
    MetadataUnavailableError,
    RepositoryView,
    UnknownRoleError,
    load_delegated_role,
    load_repository,
    resolve_trusted_root,
)

logger = logging.getLogger(__name__)

OVERVIEW_KEY = "overview"

_NOT_READY_MESSAGES = {
    RepositoryState.NOT_INITIALISED: (
        "This repository has not been set up yet. "
        "No signed metadata exists to display."
    ),
    RepositoryState.INITIALISING: (
        "The bootstrap ceremony has started. "
        "This page will show the repository once it finishes."
    ),
    RepositoryState.AWAITING_SIGNATURES: (
        "The repository is waiting for signatures before it can be used."
    ),
}


class TrustAnchorMissingError(RuntimeError):
    """No trust anchor could be established, so nothing can be checked."""


def _trust_dir(metadata_url: str) -> Path:
    """Give each repository its own directory of verified files.

    Named after the repository it belongs to, following the convention the
    RSTUF client already uses, so serving a second repository never means
    two of them sharing one cache.
    """
    digest = sha256(metadata_url.encode()).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / "rstuf-visualizer" / digest


class VisualizerService:
    """Reads one repository, and reuses the result briefly."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = TTLCache(settings.cache_ttl_seconds)
        self._trust_dir = _trust_dir(settings.metadata_url)
        self._rstuf = (
            RstufClient(settings.api_url, settings.request_timeout_seconds)
            if settings.api_url
            else None
        )

    async def _trust_anchor(self) -> bytes:
        """Establish the one root everything else is checked against.

        Three sources, tried in order: a root the operator pinned, the root
        RSTUF publishes, and nothing. Trust-on-first-use is not among them —
        a visualizer that displays unverified metadata is worse than none,
        because it states a falsehood confidently.
        """
        if self._settings.trusted_root:
            return resolve_trusted_root(
                self._settings.trusted_root,
                self._settings.request_timeout_seconds,
            )

        if self._rstuf is not None:
            published = await self._rstuf.trusted_root()
            if published:
                logger.info("Using the trust anchor published by RSTUF")
                return published

        raise TrustAnchorMissingError(
            "No trust anchor is available. Set RSTUF_TRUSTED_ROOT, or point "
            "RSTUF_API_URL at a deployment that publishes one."
        )

    async def _repository_state(self) -> RepositoryState:
        """Ask RSTUF how far the repository has been set up.

        With no API configured there is nothing to ask, so the metadata is
        taken at face value: if it verifies, the repository exists.
        """
        if self._rstuf is None:
            return RepositoryState.READY

        bootstrapped, state = await self._rstuf.bootstrap_state()
        if state == "pre":
            return RepositoryState.INITIALISING
        if state == "signing":
            return RepositoryState.AWAITING_SIGNATURES
        if bootstrapped or state == "finished":
            return RepositoryState.READY
        return RepositoryState.NOT_INITIALISED

    async def _load(self) -> RepositoryView:
        """Run one verification pass against the repository."""
        anchor = await self._trust_anchor()
        return await load_repository(
            metadata_url=self._settings.metadata_url,
            trust_dir=self._trust_dir,
            bootstrap=anchor,
        )

    async def view(self, refresh: bool = False) -> RepositoryView:
        """Return a verified view, reusing a recent one unless asked not to."""
        if refresh:
            self._cache.clear()
        return await self._cache.get_or_build(OVERVIEW_KEY, self._load)

    async def overview(self, refresh: bool = False) -> OverviewResponse:
        """Describe the repository for the first render."""
        state = await self._repository_state()
        if state is not RepositoryState.READY:
            return OverviewResponse(
                state=state, message=_NOT_READY_MESSAGES[state]
            )

        view = await self.view(refresh=refresh)
        return read.build_overview(view, state)

    async def role(self, name: str) -> RoleDetailResponse:
        """Describe one role, fetching it only if it is delegated."""
        view = await self.view()

        if any(role.name == name for role in view.roles):
            return read.build_role_detail(view, name)

        if name not in view.delegated and view.verification_error:
            # The delegation list lives in targets, which this repository
            # never got as far as verifying, so say that rather than claim
            # the role does not exist.
            raise UnknownRoleError(
                f"'{name}' could not be resolved: verification stopped at "
                f"{view.verification_error}"
            )

        loaded = await load_delegated_role(
            self._settings.metadata_url,
            view,
            name,
            self._settings.request_timeout_seconds,
        )
        return read.build_delegated_detail(view, loaded)

    async def roots(self, limit: int = DEFAULT_HISTORY) -> RootsResponse:
        """Report root's history, and whether each rotation in it holds up.

        The walk starts from the root the client verified, so the history is
        keyed by that version: publishing a new root retires the cached answer
        rather than leaving a stale chain on the page.
        """
        view = await self.view()
        trusted = view.documents.get("root")
        if trusted is None:
            raise MetadataUnavailableError("root metadata is not available")

        async def build() -> RootHistory:
            return await load_root_history(
                self._settings.metadata_url,
                trusted,
                limit,
                self._settings.request_timeout_seconds,
            )

        history = await self._cache.get_or_build(
            f"roots:{trusted.signed.version}:{limit}", build
        )
        return read.build_root_history(history)

    async def artifacts(
        self, search: str = "", page: int = 1, page_size: int = 50
    ) -> ArtifactsResponse:
        """List artifacts, gathering them from the roles that declare them.

        Delegated roles are fetched here because listing artifacts is exactly
        the request that needs their contents. Opening the page is the
        consent; loading them at startup would not be.
        """
        view = await self.view()
        collected: list[ArtifactSummary] = []

        for role in view.roles:
            document = view.documents.get(role.name)
            if document is None:
                continue
            for path, target in getattr(
                document.signed, "targets", {}
            ).items():
                collected.append(
                    ArtifactSummary(
                        path=path,
                        length=target.length,
                        hashes=dict(target.hashes),
                        role=role.name,
                    )
                )

        for name in sorted(view.delegated):
            try:
                loaded = await load_delegated_role(
                    self._settings.metadata_url,
                    view,
                    name,
                    self._settings.request_timeout_seconds,
                )
            except MetadataUnavailableError as exc:
                logger.info(
                    "Skipping %s while listing artifacts: %s", name, exc
                )
                continue
            for path, length, hashes in loaded.artifacts:
                collected.append(
                    ArtifactSummary(
                        path=path, length=length, hashes=hashes, role=name
                    )
                )

        if search:
            needle = search.lower()
            collected = [a for a in collected if needle in a.path.lower()]

        collected.sort(key=lambda item: item.path)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return ArtifactsResponse(
            total=len(collected),
            page=page,
            page_size=page_size,
            artifacts=collected[start:end],
        )

    async def status(self) -> StatusResponse:
        """Report live repository status, without letting it break the page."""
        if self._rstuf is None:
            return StatusResponse(
                available=False,
                message="No RSTUF API is configured for this deployment.",
            )

        reported = await self._rstuf.status()
        keys: list = []
        if reported.available:
            try:
                view = await self.view()
                keys = list(
                    read.key_summaries(view.documents.get("root")).values()
                )
            except (MetadataUnavailableError, TrustAnchorMissingError):
                keys = []

        return StatusResponse(
            available=reported.available,
            state=reported.state,
            bootstrap=reported.bootstrap,
            awaiting_signatures=reported.awaiting_signatures,
            keys=keys,
            message=reported.message,
        )


@lru_cache
def get_service() -> VisualizerService:
    """Return the shared service, built once per process."""
    return VisualizerService(get_settings())


__all__ = [
    "TrustAnchorMissingError",
    "UnknownRoleError",
    "VisualizerService",
    "get_service",
]
