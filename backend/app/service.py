# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What the endpoints call.

Holds the pieces a request needs — settings, the cache, the trust directory,
and the RSTUF API client — so the routes stay thin and the ordering rules
live in one place.
"""

from __future__ import annotations

import asyncio
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
    DelegatedView,
    MetadataUnavailableError,
    RepositoryView,
    UnknownRoleError,
    load_delegated_role,
    load_repository,
    resolve_trusted_root,
)

logger = logging.getLogger(__name__)

OVERVIEW_KEY = "overview"

# How many delegated roles to fetch at once when gathering artifacts. Enough
# to hide the round trips, few enough that a repository with two hundred and
# fifty-six bins does not arrive at the storage server all at the same moment.
DELEGATED_FETCH_LIMIT = 8

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

    @staticmethod
    def _is_top_level(view: RepositoryView, name: str) -> bool:
        return any(role.name == name for role in view.roles)

    async def _delegated(
        self, view: RepositoryView, name: str
    ) -> DelegatedView:
        """Fetch and check one delegated role, explaining a broken chain."""
        if name not in view.delegated and view.verification_error:
            # The delegation list lives in targets, which this repository
            # never got as far as verifying, so say that rather than claim
            # the role does not exist.
            raise UnknownRoleError(
                f"'{name}' could not be resolved: verification stopped at "
                f"{view.verification_error}"
            )

        return await load_delegated_role(
            self._settings.metadata_url,
            view,
            name,
            self._settings.request_timeout_seconds,
        )

    async def role(self, name: str) -> RoleDetailResponse:
        """Describe one role, fetching it only if it is delegated."""
        view = await self.view()

        if self._is_top_level(view, name):
            return read.build_role_detail(view, name)

        loaded = await self._delegated(view, name)
        return read.build_delegated_detail(view, loaded)

    async def raw_metadata(self, name: str) -> bytes:
        """Return the bytes one role was verified from.

        A top-level role is read back from the trust directory, which is
        where the client wrote what it accepted. A delegated role is fetched
        and checked now, and the bytes that passed that check are the ones
        returned. Either way the reader sees the document this service
        described, not a later fetch that nobody looked at.
        """
        view = await self.view()

        if self._is_top_level(view, name):
            path = self._trust_dir / f"{name}.json"
            if not path.is_file():
                raise MetadataUnavailableError(
                    f"the verified copy of {name} is no longer on disk"
                )
            return path.read_bytes()

        return (await self._delegated(view, name)).raw

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

    async def _gather_artifacts(
        self, view: RepositoryView
    ) -> list[ArtifactSummary]:
        """Read every artifact the repository vouches for, once.

        Delegated roles are fetched here because listing artifacts is exactly
        the request that needs their contents. Opening the page is the
        consent; loading them at startup would not be.

        A bin that cannot be fetched is left out and logged. One unreachable
        bin should cost its own artifacts, not the whole listing.
        """
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

        limiter = asyncio.Semaphore(DELEGATED_FETCH_LIMIT)

        async def fetch(name: str) -> tuple[str, DelegatedView | None]:
            async with limiter:
                try:
                    return name, await self._delegated(view, name)
                except MetadataUnavailableError as exc:
                    logger.info(
                        "Skipping %s while listing artifacts: %s", name, exc
                    )
                    return name, None

        results = await asyncio.gather(
            *(fetch(name) for name in sorted(view.delegated))
        )

        for name, loaded in results:
            if loaded is None:
                continue
            for path, length, hashes in loaded.artifacts:
                collected.append(
                    ArtifactSummary(
                        path=path, length=length, hashes=hashes, role=name
                    )
                )

        collected.sort(key=lambda item: item.path)
        return collected

    async def artifacts(
        self, search: str = "", page: int = 1, page_size: int = 50
    ) -> ArtifactsResponse:
        """Return one page of the repository's artifacts.

        The gathered list is kept against the version of snapshot it was read
        from, because snapshot pins every delegated role. Turning a page or
        typing in the search box therefore reads what is already in hand,
        instead of asking the storage server for every bin again.
        """
        view = await self.view()
        snapshot = view.documents.get("snapshot")
        version = getattr(snapshot.signed, "version", 0) if snapshot else 0

        collected = await self._cache.get_or_build(
            f"artifacts:{version}", lambda: self._gather_artifacts(view)
        )

        if search:
            needle = search.lower()
            # A new list, so the cached one is never narrowed in place.
            collected = [a for a in collected if needle in a.path.lower()]

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
