# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Read-only calls to the RSTUF API.

The API answers questions the signed metadata cannot: whether the repository
has been set up, what is waiting to be signed, and where the trust anchor
lives. None of it is a security claim, so none of it is verified, and a
failure here hides one panel rather than stopping the service.

Nothing in this module writes. Changing a repository is the RSTUF API's own
job, reached with the operator's credentials, not ours.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.dto.schemas import RepositoryState

logger = logging.getLogger(__name__)


def _root_bytes(value: Any) -> bytes:
    """Turn a published trust anchor into root metadata bytes.

    The API sends the document itself; a configuration file holds it base64
    encoded. Anything that is not valid base64 is taken to be the document
    already, which is the case the API exercises.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value).encode("utf-8")

    if isinstance(value, bytes):
        return value

    text = str(value).strip()
    if text.startswith("{"):
        return text.encode("utf-8")

    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return text.encode("utf-8")


# RSTUF reports how far a ceremony has progressed. Anything else, including
# no answer at all, means the repository is not ready to be drawn.
_STATE_BY_BOOTSTRAP = {
    "pre": RepositoryState.INITIALISING,
    "signing": RepositoryState.AWAITING_SIGNATURES,
    "finished": RepositoryState.READY,
}


@dataclass
class RepositoryStatus:
    """What the RSTUF API says about the repository right now."""

    available: bool = False
    state: RepositoryState = RepositoryState.NOT_INITIALISED
    bootstrap: str | None = None
    awaiting_signatures: list[str] = field(default_factory=list)
    message: str | None = None


class RstufClient:
    """A small client for the handful of endpoints this service reads."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _get(self, path: str) -> dict[str, Any] | None:
        """Return a decoded response, or None when the API cannot answer."""
        url = f"{self._base}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("RSTUF API did not answer %s: %s", url, exc)
            return None

    async def bootstrap_state(self) -> tuple[bool, str | None] | None:
        """Report whether the repository has been bootstrapped, and how far.

        ``None`` means the API did not answer, which is a different thing
        from an answer of "not bootstrapped" and must not be read as one.

        The state is a separate field from the flag: a repository part way
        through a ceremony reports ``bootstrap`` false while still having a
        state worth showing.
        """
        payload = await self._get("/api/v1/bootstrap/")
        if payload is None:
            return None
        data = payload.get("data") or {}
        return bool(data.get("bootstrap")), data.get("state")

    async def settings(self) -> dict[str, Any]:
        """Return the repository's configuration, empty when unavailable."""
        payload = await self._get("/api/v1/config/")
        if payload is None:
            return {}
        return payload.get("data") or {}

    async def trusted_root(self) -> bytes | None:
        """Return the trust anchor RSTUF publishes, when it publishes one.

        Taking the anchor from the API is weaker than an operator handing it
        over, because it arrives from the same deployment. It is stronger than
        taking it from the storage being checked, and it needs no setup.

        Two forms are accepted. The API sends the root metadata itself, as
        JSON, while the RSTUF client's own configuration file holds it base64
        encoded. Both are the same document, so both are read rather than one
        being declared correct.
        """
        value = (await self.settings()).get("trusted_root")
        if value is None:
            return None
        return _root_bytes(value)

    async def awaiting_signatures(self) -> list[str]:
        """Name the roles that still need signatures.

        When nothing is pending the API omits the ``data`` field entirely
        rather than sending an empty one, so its absence is handled instead of
        being read as a list.
        """
        payload = await self._get("/api/v1/metadata/sign")
        if payload is None:
            return []
        data = payload.get("data") or {}
        metadata = data.get("metadata") or {}
        return sorted(metadata)

    async def status(self) -> RepositoryStatus:
        """Gather everything the status panel shows, in one pass."""
        payload = await self._get("/api/v1/bootstrap/")
        if payload is None:
            return RepositoryStatus(
                available=False,
                message="The RSTUF API could not be reached.",
            )

        data = payload.get("data") or {}
        bootstrap = data.get("state")
        state = _STATE_BY_BOOTSTRAP.get(
            bootstrap or "", RepositoryState.NOT_INITIALISED
        )
        if state is RepositoryState.NOT_INITIALISED and data.get("bootstrap"):
            # Older deployments report the flag without naming a state.
            state = RepositoryState.READY

        pending: list[str] = []
        if state is not RepositoryState.NOT_INITIALISED:
            pending = await self.awaiting_signatures()

        return RepositoryStatus(
            available=True,
            state=state,
            bootstrap=bootstrap,
            awaiting_signatures=pending,
            message=payload.get("message"),
        )
