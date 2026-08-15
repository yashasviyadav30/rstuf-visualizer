# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Fetch and verify a repository's TUF metadata.

The top-level chain is ``tuf.ngclient.Updater``'s work, the client shipped
with python-tuf. It resolves root, timestamp, snapshot and targets, checks
signatures, thresholds, expiry and rollback, and writes what it accepted into
a local trust directory. This module reads those files back to describe the
repository.

A delegated role is different: the client fetches one only when a target is
being downloaded, and nothing here downloads targets. So a bin asked for by
name is fetched here and put through the same three questions the library
asks of it — does its parent's delegation entry accept the signatures, does
its version match what snapshot pins, and do the length and hashes snapshot
records agree. Every one of those is a library call. The judgement is the
library's; only the order is ours.
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
from tuf.api.exceptions import (
    DownloadError,
    LengthOrHashMismatchError,
    RepositoryError,
)
from tuf.api.metadata import Metadata
from tuf.ngclient import Updater, UpdaterConfig

from app.dto.schemas import RoleStatus

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
    raw: bytes = b""
    """The bytes that were checked, kept so they can be shown unaltered."""


@dataclass
class RepositoryView:
    """The whole repository, as far as it could be resolved."""

    roles: list[RoleView] = field(default_factory=list)
    verification_error: str | None = None
    documents: dict[str, Metadata] = field(default_factory=dict)
    delegated: dict[str, int | None] = field(default_factory=dict)
    checked_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    """When this reading was taken.

    Recorded on the reading itself, never worked out afterwards. A view
    is served from the cache long after it was built, so the page has to
    report when the repository was read; deriving that from how much time has
    passed samples two different clocks and lands a few microseconds apart on
    every call.
    """

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
        if text.startswith("http://"):
            # Everything else is checked against what this returns, and
            # nothing checks this.
            logger.warning("The trust anchor is fetched over plain HTTP")
        logger.info("Fetching the trust anchor from %s", text)
        return fetch_within(
            text,
            limit=ROOT_MAX_BYTES,
            timeout=timeout,
            what="the trust anchor",
        )

    return decoded


# What one delegated role may weigh. The library applies the same figure to
# targets metadata, and a bin is targets metadata; matching it means storage
# meets one limit whichever path asked for the file.
DELEGATED_MAX_BYTES = 5_000_000

# The library's own ceiling for root metadata, applied to the anchor too.
ROOT_MAX_BYTES = 512_000


def fetch_within(url: str, *, limit: int, timeout: float, what: str) -> bytes:
    """Fetch a file, and stop reading once it passes ``limit``.

    Reading a whole response and then measuring it is not a limit. By the time
    the length is known the bytes are already held, and how many there are was
    decided by a storage server this service does not control.

    The declared length is checked first, because a server that is honest
    about being too large saves the transfer entirely. It is not trusted: the
    body is counted as it arrives either way.
    """
    received = bytearray()
    too_large = MetadataUnavailableError(
        f"{what} is larger than the {limit} bytes this service will read"
    )

    try:
        with httpx.stream("GET", url, timeout=timeout) as response:
            response.raise_for_status()

            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > limit:
                        raise too_large
                except ValueError:
                    # A length that is not a number tells us nothing, and the
                    # count below does not depend on it.
                    pass

            for chunk in response.iter_bytes():
                received += chunk
                if len(received) > limit:
                    raise too_large
    except httpx.HTTPError as exc:
        raise MetadataUnavailableError(
            f"{what} could not be fetched from {url}"
        ) from exc

    return bytes(received)


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


# What the client will accept from a storage server we do not control.
#
# The length caps bound how much is read before giving up, so a server
# cannot answer a request for timestamp.json with an endless stream. The
# numbers are generous for real metadata: a repository with two hundred and
# fifty-six bins has a snapshot listing all of them, and it is nowhere near
# two megabytes.
#
# max_root_rotations is what makes pinning a root safe to do once and leave
# alone. The client walks forward from whatever version it was handed,
# checking each rotation against the one before it, and this is how far it
# will walk before deciding something is wrong.
#
# app_user_agent lets an operator recognise us in their access logs, which
# matters when the storage server belongs to someone else.
UPDATER_CONFIG = UpdaterConfig(
    max_root_rotations=256,
    max_delegations=32,
    root_max_length=512_000,
    timestamp_max_length=16_384,
    snapshot_max_length=2_000_000,
    targets_max_length=5_000_000,
    app_user_agent="rstuf-visualizer/0.1.0",
)


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
        config=UPDATER_CONFIG,
    )
    updater.refresh()


async def load_repository(
    metadata_url: str,
    trust_dir: Path,
    bootstrap: bytes | None,
) -> RepositoryView:
    """Verify the repository and describe what was found.

    Metadata that fails verification is reported, not raised: showing a
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


def _pin_mismatch(
    view: RepositoryView,
    name: str,
    child: Metadata,
    raw: bytes,
) -> str | None:
    """Check a delegated role against the entry snapshot pins for it.

    A correct signature says the file is genuine. It does not say the file is
    current, and an old bin signed by the same key verifies perfectly while
    listing artifacts that were withdrawn. Snapshot names the version, and
    where the repository publishes them, the length and hashes. That entry is
    what makes rollback visible, so it is checked and not merely read to
    build a URL.

    Returns the wording for the mismatch, or ``None`` when it agrees.
    """
    snapshot = view.documents.get("snapshot")
    meta = getattr(snapshot.signed, "meta", {}).get(f"{name}.json")
    if meta is None:
        return None

    if meta.version is not None and child.signed.version != meta.version:
        return (
            f"{name} is at version {child.signed.version}, and snapshot "
            f"pins version {meta.version}"
        )

    try:
        meta.verify_length_and_hashes(raw)
    except LengthOrHashMismatchError as exc:
        return f"{name} does not match what snapshot records for it: {exc}"

    return None


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
    # fetched, so a nonsense name gets a nonsense-name answer. Nothing here
    # reports it as an infrastructure failure.
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

    # Kept, because these are the bytes the parent is about to check, and
    # the bytes this service will serve if anyone asks to see the file.
    raw = fetch_within(
        url, limit=DELEGATED_MAX_BYTES, timeout=timeout, what=name
    )
    child: Metadata = Metadata.from_bytes(raw)

    result = targets.signed.get_verification_result(
        name, child.signed_bytes, child.signatures
    )
    pinned = _pin_mismatch(view, name, child, raw)

    now = datetime.now(timezone.utc)
    if not result.verified:
        status = RoleStatus.INVALID
        note = (
            f"{name} was signed by {len(result.signed)} of "
            f"{result.threshold} required keys"
        )
    elif pinned is not None:
        status = RoleStatus.INVALID
        note = pinned
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
        raw=raw,
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
