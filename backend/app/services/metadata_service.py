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
from collections import Counter
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from app.client.rstuf_api_client import RstufApiClient
from app.client.tuf_client import (
    DelegatedView,
    MetadataUnavailableError,
    RepositoryView,
    UnknownRoleError,
    load_delegated_role,
    load_repository,
    resolve_trusted_root,
)
from app.config import Settings, get_settings
from app.dto.schemas import (
    ArtifactBinsResponse,
    ArtifactsResponse,
    ArtifactSummary,
    BinSummary,
    OverviewResponse,
    RepositoryState,
    RoleDetailResponse,
    RootsResponse,
    StatusResponse,
)
from app.repositories.root_repository import (
    DEFAULT_HISTORY,
    RootHistory,
    load_root_history,
)
from app.services import presenters
from app.services.cache_service import TTLCache

logger = logging.getLogger(__name__)

OVERVIEW_KEY = "overview"

# How many delegated roles to fetch at once when gathering artifacts. Enough
# to hide the round trips, few enough that a repository with two hundred and
# fifty-six bins does not arrive at the storage server all at the same moment.
DELEGATED_FETCH_LIMIT = 8

# How recently the repository must have been read for a refresh to be turned
# away. A visible button gets pressed by everyone who opens the page, every
# time, so the cache only survives if the server declines the ones that cannot
# tell it anything new. The repository's own worker renews metadata every few
# minutes, so nothing is lost by declining a second look after five seconds.
MIN_REFRESH_SECONDS = 5.0

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


class MetadataService:
    """Reads one repository, and reuses the result briefly."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = TTLCache(settings.cache_ttl_seconds)
        self._trust_dir = _trust_dir(settings.metadata_url)
        self._rstuf = (
            RstufApiClient(settings.api_url, settings.request_timeout_seconds)
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

        reported = await self._rstuf.bootstrap_state()
        if reported is None:
            # The API is advisory; the signed metadata is the evidence. An
            # API that cannot be reached says nothing about whether the
            # repository exists, so reading its silence as "not set up"
            # would hide a repository that is right there and checkable.
            logger.info(
                "The RSTUF API did not answer; reading the metadata anyway"
            )
            return RepositoryState.READY

        bootstrapped, state = reported
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
        """Return a verified view, reusing a recent one unless asked not to.

        A refresh only counts when the answer in hand is old enough that a
        new one could differ. Everyone who opens the page presses that button,
        and honouring every press would mean a full verification pass per
        visitor while the repository itself has not moved.
        """
        if refresh:
            age = self._cache.age(OVERVIEW_KEY)
            if age is None or age >= MIN_REFRESH_SECONDS:
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
        return presenters.build_overview(view, state)

    @staticmethod
    def _is_top_level(view: RepositoryView, name: str) -> bool:
        return any(role.name == name for role in view.roles)

    async def _delegated(
        self, view: RepositoryView, name: str
    ) -> DelegatedView:
        """Fetch and check one delegated role, explaining a broken chain."""
        if name not in view.delegated and view.verification_error:
            # The delegation list lives in targets, which this repository
            # never got as far as verifying. Saying the role does not exist
            # would be a claim this pass cannot support.
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
            return presenters.build_role_detail(view, name)

        loaded = await self._delegated(view, name)
        return presenters.build_delegated_detail(view, loaded)

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
        instead of leaving a stale chain on the page.
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
        return presenters.build_root_history(history)

    async def _gather_artifacts(
        self, view: RepositoryView
    ) -> tuple[list[ArtifactSummary], list[str]]:
        """Read every artifact the repository vouches for, once.

        Delegated roles are fetched here because listing artifacts is exactly
        the request that needs their contents. Opening the page is the
        consent; loading them at startup would not be.

        Returns what was read and the names of the roles that could not be.
        Delegated roles are siblings, never a chain, so one unreachable
        bin costs its own artifacts and no others. It is named in the answer,
        because a list quietly short of a hundred entries is worse than a list
        that says which hundred are missing.
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

        unavailable: list[str] = []
        for name, loaded in results:
            if loaded is None:
                unavailable.append(name)
                continue
            for path, length, hashes in loaded.artifacts:
                collected.append(
                    ArtifactSummary(
                        path=path, length=length, hashes=hashes, role=name
                    )
                )

        collected.sort(key=lambda item: item.path)
        return collected, unavailable

    async def _artifact_index(
        self, view: RepositoryView
    ) -> tuple[list[ArtifactSummary], list[str]]:
        """Every artifact in the repository, read once and kept.

        Held against the version of snapshot it was read from, because
        snapshot pins every delegated role: a change to any bin moves that
        number. Counting bins, opening one, searching and turning pages all
        read this, so only the first of them asks the storage server.
        """
        snapshot = view.documents.get("snapshot")
        version = getattr(snapshot.signed, "version", 0) if snapshot else 0
        return await self._cache.get_or_build(
            f"artifacts:{version}", lambda: self._gather_artifacts(view)
        )

    async def artifact_bins(self) -> ArtifactBinsResponse:
        """Name every role holding artifacts, with how many it holds.

        The browser asks for this before asking for artifacts, so a
        repository of 256 bins costs one screen of counts instead of a
        table nobody can read.
        """
        view = await self.view()
        collected, unavailable = await self._artifact_index(view)

        counts = Counter(item.role for item in collected)
        # Delegated roles that hold nothing still belong on the list. An
        # operator reading "0" learns the bin exists and is empty, which is
        # not what its absence would have told them.
        names = sorted(set(view.delegated) | set(counts) | set(unavailable))

        return ArtifactBinsResponse(
            total=len(collected),
            bins=[
                BinSummary(
                    name=name,
                    count=counts.get(name, 0),
                    available=name not in unavailable,
                )
                for name in names
            ],
        )

    async def artifacts(
        self,
        search: str = "",
        role: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> ArtifactsResponse:
        """Return one page of artifacts, from one role or from all of them.

        Narrowing to a role serves the bin a reader has just opened; leaving
        it empty serves a search, which has to span every bin because a name
        gives no clue which one holds it.
        """
        view = await self.view()
        collected, unavailable = await self._artifact_index(view)

        if role:
            # A new list each time, so the cached one is never narrowed
            # in place and the next reader still sees everything.
            collected = [a for a in collected if a.role == role]
        if search:
            needle = search.lower()
            collected = [a for a in collected if needle in a.path.lower()]

        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return ArtifactsResponse(
            total=len(collected),
            page=page,
            page_size=page_size,
            artifacts=collected[start:end],
            unavailable=unavailable,
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
                root = view.documents.get("root")
                keys = list(presenters.key_summaries(root).values())
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
def get_metadata_service() -> MetadataService:
    """Return the shared service, built once per process."""
    return MetadataService(get_settings())


__all__ = [
    "TrustAnchorMissingError",
    "UnknownRoleError",
    "MetadataService",
    "get_metadata_service",
]
