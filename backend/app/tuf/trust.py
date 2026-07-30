"""Fetch and verify a repository's TUF metadata.

Verification is delegated to ``tuf.ngclient.Updater``, the client shipped with
python-tuf. It resolves the metadata chain, checks signatures, thresholds,
expiry and rollback, and writes the verified files into a local trust
directory. This module reads those verified files back to describe the
repository; it never validates metadata itself.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tuf.api.exceptions import DownloadError, RepositoryError
from tuf.api.metadata import Metadata
from tuf.ngclient import Updater

from app.models.schemas import RoleStatus

logger = logging.getLogger(__name__)

TOP_LEVEL_ROLES = ("root", "timestamp", "snapshot", "targets")


class MetadataUnavailableError(RuntimeError):
    """The metadata could not be retrieved at all.

    Distinct from metadata that was retrieved but failed verification: a
    download failure is an infrastructure problem, whereas broken trust is
    something the interface is meant to display.
    """


@dataclass
class RoleView:
    """One verified role, as read back from the trust directory."""

    name: str
    version: int
    expires: datetime
    status: RoleStatus
    threshold: int | None = None
    key_count: int | None = None
    delegates_to: list[str] = field(default_factory=list)


@dataclass
class RepositoryView:
    """The whole repository, as far as it could be resolved."""

    roles: list[RoleView] = field(default_factory=list)
    verification_error: str | None = None

    @property
    def is_trustworthy(self) -> bool:
        return self.verification_error is None


def resolve_trusted_root(value: str, timeout: float = 10.0) -> bytes:
    """Turn the configured trust anchor into root metadata bytes.

    Following the RSTUF client convention, the setting is base64 encoded and
    may hold either the root metadata itself or a URL pointing at it.
    """
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("trusted root is not valid base64") from exc

    text = decoded.decode("utf-8", errors="replace").strip()
    if text.startswith(("http://", "https://")):
        logger.info("Fetching the trust anchor from %s", text)
        try:
            response = httpx.get(text, timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MetadataUnavailableError(
                f"could not fetch the trust anchor from {text}"
            ) from exc
        return response.content

    return decoded


def _status_for(metadata: Metadata, now: datetime) -> RoleStatus:
    """Classify a role that the client already accepted as correctly signed."""
    return RoleStatus.EXPIRED if metadata.signed.expires < now else RoleStatus.VALID


def _delegated_names(targets: Metadata) -> list[str]:
    """List the roles ``targets`` delegates to, whatever form they take.

    Delegations are declared either as named roles or as a succinct-roles
    rule that generates the names. Both are resolved by the library, so the
    caller never assumes a naming scheme or a bin count.
    """
    delegations = getattr(targets.signed, "delegations", None)
    if delegations is None:
        return []

    if delegations.succinct_roles is not None:
        return list(delegations.succinct_roles.get_roles())

    return list(delegations.roles or [])


def _read_trust_directory(trust_dir: Path) -> list[RoleView]:
    """Describe every role the client verified and cached."""
    now = datetime.now(timezone.utc)
    views: list[RoleView] = []

    root_path = trust_dir / "root.json"
    root = Metadata.from_file(str(root_path)) if root_path.exists() else None

    for path in sorted(trust_dir.glob("*.json")):
        name = path.stem
        try:
            metadata = Metadata.from_file(str(path))
        except Exception:  # noqa: BLE001 - a cached file we cannot parse
            logger.warning("Skipping unreadable cached metadata: %s", path.name)
            continue

        role = root.signed.roles.get(name) if root and name in TOP_LEVEL_ROLES else None

        views.append(
            RoleView(
                name=name,
                version=metadata.signed.version,
                expires=metadata.signed.expires,
                status=_status_for(metadata, now),
                threshold=role.threshold if role else None,
                key_count=len(role.keyids) if role else None,
                delegates_to=_delegated_names(metadata) if name == "targets" else [],
            )
        )

    return views


def _refresh(trust_dir: Path, metadata_url: str, bootstrap: bytes | None) -> None:
    """Run the client's verification pass. Blocking, so keep it off the loop."""
    updater = Updater(
        metadata_dir=str(trust_dir),
        metadata_base_url=metadata_url,
        bootstrap=bootstrap,
    )
    updater.refresh()


async def load_repository(
    metadata_url: str,
    trust_dir: Path,
    bootstrap: bytes | None,
) -> RepositoryView:
    """Verify the repository and describe what was found.

    Metadata that fails verification is reported rather than raised: showing a
    repository in trouble is the purpose of this service. Only an unreachable
    repository raises, because then there is nothing to show at all.
    """
    trust_dir.mkdir(parents=True, exist_ok=True)
    verification_error: str | None = None

    try:
        # Updater performs synchronous I/O, so it runs on a worker thread to
        # keep the event loop free for other requests.
        await asyncio.to_thread(_refresh, trust_dir, metadata_url, bootstrap)
    except DownloadError as exc:
        raise MetadataUnavailableError(str(exc)) from exc
    except RepositoryError as exc:
        # Expired, unsigned, or rolled back. Whatever was verified up to this
        # point is still cached, so the interface can show how far it got.
        verification_error = str(exc)
        logger.info("Repository failed verification: %s", exc)

    roles = _read_trust_directory(trust_dir)
    if not roles and verification_error:
        raise MetadataUnavailableError(verification_error)

    return RepositoryView(roles=roles, verification_error=verification_error)
