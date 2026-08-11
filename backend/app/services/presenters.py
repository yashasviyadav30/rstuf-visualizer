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
from urllib.parse import quote

from tuf.api.metadata import Metadata

from app.client.tuf_client import DelegatedView, RepositoryView
from app.dto.schemas import (
    ArtifactSummary,
    DelegatedSummary,
    ExpiryBand,
    KeyChangeAction,
    KeySummary,
    OverviewResponse,
    RepositoryState,
    RoleDetailResponse,
    RoleStatus,
    RoleSummary,
    RootKeyChange,
    RootRoleChange,
    RootsResponse,
    RootVersionSummary,
    SignatureCheckSummary,
    TreeEdge,
)
from app.repositories.root_repository import (
    RootHistory,
    RootRevision,
    SignatureCheck,
)

RSTUF_KEY_NAME = "x-rstuf-key-name"
RSTUF_ONLINE_KEY_URI = "x-rstuf-online-key-uri"

# A day and a week. Timestamp is renewed roughly daily, so the shorter band
# is the one that separates "working normally" from "nobody is renewing this".
CRITICAL_SECONDS = 24 * 60 * 60
EXPIRING_SECONDS = 7 * CRITICAL_SECONDS


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def raw_url(name: str) -> str:
    """Address the verified bytes for one role, on this service.

    Not a link to the storage the files came from. The reader may not be able
    to reach that address, and a fresh fetch from it would return whatever is
    there now, unchecked. Serving the copy this service verified means the
    link shows the document the page is describing.
    """
    return f"/api/v1/roles/{quote(name, safe='')}/raw"


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
        checked_at=view.checked_at.isoformat(),
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
        signatures_present=_valid_signatures(view, name),
        signed_by=[
            keys[keyid] for keyid in _keyids_for(view, name) if keyid in keys
        ],
        delegates_to=role.delegates_to,
        artifacts=artifacts,
        raw_url=raw_url(name),
    )


def _valid_signatures(view: RepositoryView, name: str) -> int | None:
    """Count the signatures on a top-level role that root accepts.

    Counted rather than assumed. The client verified this role during the
    refresh, so the number necessarily meets the threshold, but a screen that
    reports "2 of 2" should have counted the two: an operator reading a
    signature count is asking a question about evidence, and the honest answer
    to "how many" is never "enough".

    ``None`` where the count cannot be taken, which the interface reports as
    unknown rather than as zero.
    """
    root = view.documents.get("root")
    document = view.documents.get(name)
    if root is None or document is None:
        return None

    try:
        result = root.signed.get_verification_result(
            name, document.signed_bytes, document.signatures
        )
    except Exception:  # noqa: BLE001 - an unknown role has nothing to count
        return None

    return len(result.signed)


def _key_name(key: object, keyid: str) -> str:
    """Name a key the way RSTUF records it, or fall back to its identifier."""
    extra = getattr(key, "unrecognized_fields", None) or {}
    return extra.get(RSTUF_KEY_NAME) or keyid[:8]


def _key_changes(older: object, newer: object) -> list[RootKeyChange]:
    """List the keys one version of root added, and the ones it withdrew."""
    before = getattr(older, "keys", {}) or {}
    after = getattr(newer, "keys", {}) or {}

    changes: list[RootKeyChange] = []
    for keyid in sorted(set(after) - set(before)):
        changes.append(
            RootKeyChange(
                keyid=keyid,
                keyid_short=keyid[:8],
                name=_key_name(after[keyid], keyid),
                action=KeyChangeAction.ADDED,
            )
        )
    for keyid in sorted(set(before) - set(after)):
        changes.append(
            RootKeyChange(
                keyid=keyid,
                keyid_short=keyid[:8],
                name=_key_name(before[keyid], keyid),
                action=KeyChangeAction.REMOVED,
            )
        )
    return changes


def _role_changes(older: object, newer: object) -> list[RootRoleChange]:
    """Report where a rotation moved a threshold or changed who may sign.

    Roles that came through a rotation untouched are left out. A page listing
    four unchanged roles beside the one that moved buries the finding.
    """
    before = getattr(older, "roles", {}) or {}
    after = getattr(newer, "roles", {}) or {}
    names = {
        **(getattr(older, "keys", {}) or {}),
        **(getattr(newer, "keys", {}) or {}),
    }

    changes: list[RootRoleChange] = []
    for role in sorted(set(before) | set(after)):
        was, now_role = before.get(role), after.get(role)
        was_ids = set(was.keyids) if was else set()
        now_ids = set(now_role.keyids) if now_role else set()
        threshold_before = was.threshold if was else None
        threshold_after = now_role.threshold if now_role else None

        added = sorted(now_ids - was_ids)
        removed = sorted(was_ids - now_ids)
        if not added and not removed and threshold_before == threshold_after:
            continue

        changes.append(
            RootRoleChange(
                role=role,
                threshold_before=threshold_before,
                threshold_after=threshold_after,
                signers_added=[
                    _key_name(names.get(keyid), keyid) for keyid in added
                ],
                signers_removed=[
                    _key_name(names.get(keyid), keyid) for keyid in removed
                ],
            )
        )
    return changes


def _check_summary(check: SignatureCheck | None) -> SignatureCheckSummary:
    if check is None:  # pragma: no cover - the walk always sets this one
        return SignatureCheckSummary(verified=False, present=0, threshold=0)
    return SignatureCheckSummary(
        verified=check.verified,
        present=check.present,
        threshold=check.threshold,
    )


def _root_version(
    revision: RootRevision,
    previous: RootRevision | None,
    current: int,
    now: datetime,
) -> RootVersionSummary:
    """Describe one version of root, and what the rotation into it did."""
    superseded = revision.version != current
    if superseded:
        # A client checks expiry on the final root only, so reporting a band
        # here would raise an alarm about a file nothing depends on.
        band, phrase = None, f"superseded by version {current}"
    else:
        band, phrase = expiry_band(revision.expires, now)

    keys_changed: list[RootKeyChange] = []
    roles_changed: list[RootRoleChange] = []
    if previous is not None:
        keys_changed = _key_changes(
            previous.document.signed, revision.document.signed
        )
        roles_changed = _role_changes(
            previous.document.signed, revision.document.signed
        )

    return RootVersionSummary(
        version=revision.version,
        expires=revision.expires.isoformat(),
        expires_in=phrase,
        band=band,
        superseded=superseded,
        verified=revision.verified,
        by_own_keys=_check_summary(revision.by_own_keys),
        by_previous_keys=(
            _check_summary(revision.by_previous_keys)
            if revision.by_previous_keys is not None
            else None
        ),
        note=revision.note,
        key_count=len(getattr(revision.document.signed, "keys", {}) or {}),
        keys_changed=keys_changed,
        roles_changed=roles_changed,
    )


def build_root_history(
    history: RootHistory, now: datetime | None = None
) -> RootsResponse:
    """Assemble root's history, newest version first."""
    now = now or datetime.now(timezone.utc)
    revisions = history.revisions

    versions = [
        _root_version(
            revision,
            revisions[index + 1] if index + 1 < len(revisions) else None,
            history.current,
            now,
        )
        for index, revision in enumerate(revisions)
    ]

    return RootsResponse(
        current=history.current,
        earliest=history.earliest,
        versions=versions,
        message=history.message,
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
        raw_url=raw_url(loaded.name),
    )
