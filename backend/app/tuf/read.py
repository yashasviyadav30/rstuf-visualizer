# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Turn verified metadata into the shapes the browser receives.

Nothing here fetches or checks anything. It reads what the client already
verified and presents it: expiry as a band rather than a bare date, keys by
their names rather than their identifiers, and a tree assembled from files
that were downloaded once.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tuf.api.metadata import Metadata

from app.models.schemas import (
    ArtifactSummary,
    DelegatedSummary,
    ExpiryBand,
    KeySummary,
    OverviewResponse,
    RepositoryState,
    RoleDetailResponse,
    RoleStatus,
    RoleSummary,
    TreeEdge,
)
from app.tuf.trust import DelegatedView, RepositoryView

RSTUF_KEY_NAME = "x-rstuf-key-name"
RSTUF_ONLINE_KEY_URI = "x-rstuf-online-key-uri"

# A day and a week. Timestamp is renewed roughly daily, so the shorter band
# is the one that separates "working normally" from "nobody is renewing this".
CRITICAL_SECONDS = 24 * 60 * 60
EXPIRING_SECONDS = 7 * CRITICAL_SECONDS


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def expiry_band(
    expires: datetime, now: datetime | None = None
) -> tuple[ExpiryBand, str]:
    """Classify how close a role is to expiring, and say it in words."""
    now = now or datetime.now(timezone.utc)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    seconds = (expires - now).total_seconds()

    if seconds <= 0:
        past = abs(seconds)
        if past < CRITICAL_SECONDS:
            return ExpiryBand.EXPIRED, f"expired {int(past // 3600)}h ago"
        days = int(past // CRITICAL_SECONDS)
        return ExpiryBand.EXPIRED, f"expired {_plural(days, 'day')} ago"

    if seconds < CRITICAL_SECONDS:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return ExpiryBand.CRITICAL, f"expires in {hours}h {minutes}m"

    days = int(seconds // CRITICAL_SECONDS)
    if seconds < EXPIRING_SECONDS:
        return ExpiryBand.EXPIRING, f"expires in {_plural(days, 'day')}"

    if days > 60:
        return ExpiryBand.VALID, f"expires {expires.date().isoformat()}"
    return ExpiryBand.VALID, f"expires in {_plural(days, 'day')}"


def key_summaries(root: Metadata | None) -> dict[str, KeySummary]:
    """Describe every key root declares, by name where RSTUF supplies one.

    A sixty-four character identifier tells an operator nothing. RSTUF records
    a readable name on each key, and marks the online ones with the address of
    the service that holds them, which is what makes the offline and online
    split visible.
    """
    if root is None:
        return {}

    signs: dict[str, list[str]] = {}
    for role_name, role in root.signed.roles.items():
        for keyid in role.keyids:
            signs.setdefault(keyid, []).append(role_name)

    summaries: dict[str, KeySummary] = {}
    for keyid, key in root.signed.keys.items():
        extra = getattr(key, "unrecognized_fields", None) or {}
        summaries[keyid] = KeySummary(
            keyid=keyid,
            keyid_short=keyid[:8],
            name=extra.get(RSTUF_KEY_NAME) or keyid[:8],
            scheme=getattr(key, "scheme", ""),
            online=RSTUF_ONLINE_KEY_URI in extra,
            signs=sorted(signs.get(keyid, [])),
        )
    return summaries


def _delegation_keys(targets: Metadata | None) -> dict[str, KeySummary]:
    """Describe the keys a parent declares for the roles it delegates to.

    A delegated role is not signed by a top-level key. Its signers are named
    in the parent's own delegation entry, so reading them from root would
    report the wrong key wherever a repository gives a role its own.
    """
    if targets is None:
        return {}
    delegations = getattr(targets.signed, "delegations", None)
    if delegations is None:
        return {}

    summaries: dict[str, KeySummary] = {}
    for keyid, key in (delegations.keys or {}).items():
        extra = getattr(key, "unrecognized_fields", None) or {}
        summaries[keyid] = KeySummary(
            keyid=keyid,
            keyid_short=keyid[:8],
            name=extra.get(RSTUF_KEY_NAME) or keyid[:8],
            scheme=getattr(key, "scheme", ""),
            online=RSTUF_ONLINE_KEY_URI in extra,
        )
    return summaries


def build_overview(
    view: RepositoryView,
    state: RepositoryState = RepositoryState.READY,
    now: datetime | None = None,
) -> OverviewResponse:
    """Assemble the initial page from files the client already verified."""
    now = now or datetime.now(timezone.utc)
    keys = key_summaries(view.documents.get("root"))

    roles: list[RoleSummary] = []
    edges: list[TreeEdge] = []

    for role in view.roles:
        band, phrase = expiry_band(role.expires, now)
        named = [
            keys[keyid].name
            for keyid in _keyids_for(view, role.name)
            if keyid in keys
        ]
        roles.append(
            RoleSummary(
                name=role.name,
                version=role.version,
                expires=role.expires.isoformat(),
                expires_in=phrase,
                band=band,
                threshold=role.threshold,
                key_count=role.key_count,
                key_names=named,
                status=role.status,
            )
        )
        for child in role.delegates_to:
            edges.append(TreeEdge(parent=role.name, child=child))

    # Root authorises the other top-level roles, which is a delegation too.
    root = view.documents.get("root")
    if root is not None:
        present = {role.name for role in view.roles}
        for name in ("timestamp", "snapshot", "targets"):
            if name in present:
                edges.append(TreeEdge(parent="root", child=name))

    delegated = [
        DelegatedSummary(name=name, version=version, loaded=False)
        for name, version in sorted(view.delegated.items())
    ]

    status = RoleStatus.VALID
    if view.verification_error:
        status = (
            RoleStatus.EXPIRED
            if "expired" in view.verification_error.lower()
            else RoleStatus.INVALID
        )
    elif any(role.status is RoleStatus.EXPIRED for role in view.roles):
        status = RoleStatus.EXPIRED

    return OverviewResponse(
        state=state,
        status=status,
        checked_at=now.isoformat(),
        roles=sorted(roles, key=lambda item: _role_order(item.name)),
        delegated=delegated,
        edges=edges,
        verification_error=view.verification_error,
    )


_ROLE_ORDER = {"root": 0, "timestamp": 1, "snapshot": 2, "targets": 3}


def _role_order(name: str) -> tuple[int, str]:
    return _ROLE_ORDER.get(name, 9), name


def _keyids_for(view: RepositoryView, role_name: str) -> list[str]:
    root = view.documents.get("root")
    if root is None:
        return []
    role = root.signed.roles.get(role_name)
    return list(role.keyids) if role else []


def build_role_detail(
    view: RepositoryView, name: str, now: datetime | None = None
) -> RoleDetailResponse:
    """Describe one top-level role, already verified during the refresh."""
    now = now or datetime.now(timezone.utc)
    role = next(item for item in view.roles if item.name == name)
    keys = key_summaries(view.documents.get("root"))
    band, phrase = expiry_band(role.expires, now)

    document = view.documents.get(name)
    artifacts: list[ArtifactSummary] = []
    if document is not None:
        for path, target in sorted(
            getattr(document.signed, "targets", {}).items()
        ):
            artifacts.append(
                ArtifactSummary(
                    path=path,
                    length=target.length,
                    hashes=dict(target.hashes),
                    role=name,
                )
            )

    return RoleDetailResponse(
        name=name,
        version=role.version,
        expires=role.expires.isoformat(),
        expires_in=phrase,
        band=band,
        status=role.status,
        threshold=role.threshold,
        signed_by=[
            keys[keyid] for keyid in _keyids_for(view, name) if keyid in keys
        ],
        delegates_to=role.delegates_to,
        artifacts=artifacts,
    )


def build_delegated_detail(
    view: RepositoryView, loaded: DelegatedView, now: datetime | None = None
) -> RoleDetailResponse:
    """Describe one delegated role that was fetched and checked on request."""
    now = now or datetime.now(timezone.utc)
    band, phrase = expiry_band(loaded.expires, now)
    keys = _delegation_keys(view.documents.get("targets"))

    return RoleDetailResponse(
        name=loaded.name,
        version=loaded.version,
        expires=loaded.expires.isoformat(),
        expires_in=phrase,
        band=band,
        status=loaded.status,
        threshold=loaded.threshold,
        signed_by=[
            keys[keyid] for keyid in loaded.signing_keyids if keyid in keys
        ],
        signatures_present=loaded.signed_count,
        signature_note=loaded.note,
        delegates_to=loaded.delegates_to,
        artifacts=[
            ArtifactSummary(
                path=path,
                length=length,
                hashes=hashes,
                role=loaded.name,
            )
            for path, length, hashes in loaded.artifacts
        ],
    )
