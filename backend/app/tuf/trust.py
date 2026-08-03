# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

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
from urllib.parse import quote

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


class UnknownRoleError(LookupError):
    """The requested role is not delegated by this repository."""


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
class DelegatedView:
    """One delegated role, fetched on request and checked by its parent."""

    name: str
    version: int
    expires: datetime
    status: RoleStatus
    threshold: int
    signed_count: int
    signing_keyids: list[str] = field(default_factory=list)
    delegates_to: list[str] = field(default_factory=list)
    artifacts: list[tuple[str, int, dict[str, str]]] = field(
        default_factory=list
    )
    note: str | None = None


@dataclass
class RepositoryView:
    """The whole repository, as far as it could be resolved."""

    roles: list[RoleView] = field(default_factory=list)
    verification_error: str | None = None
    documents: dict[str, Metadata] = field(default_factory=dict)
    delegated: dict[str, int | None] = field(default_factory=dict)

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
    return (
        RoleStatus.EXPIRED
        if metadata.signed.expires < now
        else RoleStatus.VALID
    )


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


def _delegated_versions(
    documents: dict[str, Metadata],
) -> dict[str, int | None]:
    """Name every delegated role, and pin its version, without fetching it.

    The names come from the delegation rule in ``targets`` and the versions
    from ``snapshot``. Both files are already verified, so a repository with
    two hundred bins costs nothing to describe.
    """
    targets = documents.get("targets")
    if targets is None:
        return {}

    snapshot = documents.get("snapshot")
    meta = getattr(snapshot.signed, "meta", {}) if snapshot else {}

    versions: dict[str, int | None] = {}
    for name in _delegated_names(targets):
        entry = meta.get(f"{name}.json")
        versions[name] = getattr(entry, "version", None)
    return versions


def _read_trust_directory(
    trust_dir: Path,
) -> tuple[list[RoleView], dict[str, Metadata]]:
    """Describe every role the client verified and cached."""
    now = datetime.now(timezone.utc)
    views: list[RoleView] = []
    documents: dict[str, Metadata] = {}

    root_path = trust_dir / "root.json"
    root = Metadata.from_file(str(root_path)) if root_path.exists() else None

    for path in sorted(trust_dir.glob("*.json")):
        name = path.stem
        try:
            metadata = Metadata.from_file(str(path))
        except Exception:  # noqa: BLE001 - a cached file we cannot parse
            logger.warning(
                "Skipping unreadable cached metadata: %s", path.name
            )
            continue

        documents[name] = metadata
        role = (
            root.signed.roles.get(name)
            if root and name in TOP_LEVEL_ROLES
            else None
        )

        views.append(
            RoleView(
                name=name,
                version=metadata.signed.version,
                expires=metadata.signed.expires,
                status=_status_for(metadata, now),
                threshold=role.threshold if role else None,
                key_count=len(role.keyids) if role else None,
                delegates_to=(
                    _delegated_names(metadata) if name == "targets" else []
                ),
            )
        )

    return views, documents


def _refresh(
    trust_dir: Path, metadata_url: str, bootstrap: bytes | None
) -> None:
    """Run the verification pass.

    Blocking, so keep it off the event loop.
    """
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

    roles, documents = _read_trust_directory(trust_dir)
    if not roles and verification_error:
        raise MetadataUnavailableError(verification_error)

    return RepositoryView(
        roles=roles,
        verification_error=verification_error,
        documents=documents,
        delegated=_delegated_versions(documents),
    )


def _delegated_url(
    metadata_url: str, name: str, version: int | None, consistent: bool
) -> str:
    """Build the address of one delegated role's metadata file."""
    base = metadata_url if metadata_url.endswith("/") else metadata_url + "/"
    filename = quote(f"{name}.json", safe="")
    if consistent and version is not None:
        return f"{base}{version}.{filename}"
    return f"{base}{filename}"


def _fetch_delegated(
    metadata_url: str,
    view: RepositoryView,
    name: str,
    timeout: float,
) -> DelegatedView:
    """Fetch one delegated role and have its parent check it.

    The parent holds the delegation rule, so the parent does the checking.
    This uses the library's public verification interface, which also reports
    how many of the required signatures were present.
    """
    # Whether the name is a role at all is settled before anything is
    # fetched, so a nonsense name is answered as a nonsense name rather than
    # as an infrastructure failure.
    if name not in view.delegated:
        raise UnknownRoleError(name)

    targets = view.documents.get("targets")
    if targets is None:
        raise MetadataUnavailableError("targets metadata is not available")

    root = view.documents.get("root")
    consistent = bool(
        getattr(root.signed, "consistent_snapshot", True) if root else True
    )
    url = _delegated_url(
        metadata_url, name, view.delegated.get(name), consistent
    )

    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MetadataUnavailableError(
            f"could not fetch {name} from {url}"
        ) from exc

    child: Metadata = Metadata.from_bytes(response.content)

    result = targets.signed.get_verification_result(
        name, child.signed_bytes, child.signatures
    )

    now = datetime.now(timezone.utc)
    if not result.verified:
        status = RoleStatus.INVALID
        note = (
            f"{name} was signed by {len(result.signed)} of "
            f"{result.threshold} required keys"
        )
    elif child.signed.expires < now:
        status = RoleStatus.EXPIRED
        note = None
    else:
        status = RoleStatus.VALID
        note = None

    artifacts = [
        (path, target.length, dict(target.hashes))
        for path, target in getattr(child.signed, "targets", {}).items()
    ]

    return DelegatedView(
        name=name,
        version=child.signed.version,
        expires=child.signed.expires,
        status=status,
        threshold=result.threshold,
        signed_count=len(result.signed),
        signing_keyids=sorted(result.signed) + sorted(result.unsigned),
        delegates_to=_delegated_names(child),
        artifacts=sorted(artifacts),
        note=note,
    )


async def load_delegated_role(
    metadata_url: str,
    view: RepositoryView,
    name: str,
    timeout: float = 10.0,
) -> DelegatedView:
    """Load one delegated role, off the event loop."""
    return await asyncio.to_thread(
        _fetch_delegated, metadata_url, view, name, timeout
    )
