# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Walk the history of root, checking every rotation along the way.

Root is the anchor, so rotating a key means publishing a new version of it.
The specification's rotation rule is that version N must be signed to
threshold by the keys of version N-1 *and* by its own keys, which is what
makes a series of root files a chain instead of a pile.

The walk starts at the root the client already verified and moves backwards.
That direction is deliberate. Confirming that version N-1's keys signed
version N proves those keys are the genuine ones, and since N-1 is signed by
those same keys, the whole of N-1 is anchored to something already trusted.
Walking forwards from version 1 would prove nothing, because nothing vouches
for version 1 except itself.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

from tuf.api.exceptions import RepositoryError
from tuf.api.metadata import Metadata, Root

from app.client.tuf_client import (
    ROOT_MAX_BYTES,
    MetadataUnavailableError,
    fetch_within,
)

logger = logging.getLogger(__name__)

# How far back to walk unless asked otherwise. A long-lived repository may
# hold hundreds of versions, and fetching every one of them to draw a page
# nobody scrolled is work done for the repository, not for the reader.
DEFAULT_HISTORY = 20
MAX_HISTORY = 256


@dataclass
class SignatureCheck:
    """The outcome of one threshold check, with the numbers behind it."""

    verified: bool
    present: int
    threshold: int


@dataclass
class RootRevision:
    """One version of root, and the checks run against it."""

    version: int
    expires: datetime
    document: Metadata
    by_own_keys: SignatureCheck
    by_previous_keys: SignatureCheck | None = None
    note: str | None = None

    @property
    def verified(self) -> bool:
        """True when every check that applies to this version passed.

        Version one has no predecessor it could have rotated from, and nor
        does a version whose predecessor was never fetched. Both are honest
        gaps, recorded as such and never counted as failures.
        """
        if not self.by_own_keys.verified:
            return False
        if self.by_previous_keys is None:
            return True
        return self.by_previous_keys.verified


@dataclass
class RootHistory:
    """Every version of root that was read, newest first."""

    current: int
    revisions: list[RootRevision] = field(default_factory=list)
    message: str | None = None

    @property
    def earliest(self) -> int:
        return self.revisions[-1].version if self.revisions else self.current


def _root_url(metadata_url: str, version: int) -> str:
    """Build the address of one version of root.

    Root files carry their version in the filename whatever the repository's
    consistent-snapshot setting is, so there is no second form to handle.
    """
    base = metadata_url if metadata_url.endswith("/") else metadata_url + "/"
    return f"{base}{version}.root.json"


def _fetch(metadata_url: str, version: int, timeout: float) -> Metadata:
    """Retrieve one version of root, unverified."""
    url = _root_url(metadata_url, version)
    return Metadata.from_bytes(
        fetch_within(
            url,
            limit=ROOT_MAX_BYTES,
            timeout=timeout,
            what=f"version {version} of root",
        )
    )


def _check(delegator: Root, child: Metadata) -> SignatureCheck:
    """Ask one version of root whether it authorised the signatures on another.

    ``get_verification_result`` reports the outcome instead of raising it,
    which matters here: a rotation that does not verify is the finding, not an
    error to hide.
    """
    result = delegator.get_verification_result(
        Root.type, child.signed_bytes, child.signatures
    )
    return SignatureCheck(
        verified=result.verified,
        present=len(result.signed),
        threshold=result.threshold,
    )


def _rotation_note(newer: RootRevision, older: RootRevision) -> str | None:
    """Say what went wrong with one step of the chain, when something did."""
    check = newer.by_previous_keys
    if check is None or check.verified:
        return None
    return (
        f"the rotation into version {newer.version} carries {check.present} "
        f"of the {check.threshold} signatures version {older.version} "
        f"requires for it"
    )


def _walk(
    metadata_url: str,
    trusted: Metadata,
    limit: int,
    timeout: float,
) -> RootHistory:
    """Read backwards from the trusted root, checking each rotation.

    Blocking, so keep it off the event loop.
    """
    current = trusted.signed.version
    newest = RootRevision(
        version=current,
        expires=trusted.signed.expires,
        document=trusted,
        by_own_keys=_check(trusted.signed, trusted),
    )
    history = RootHistory(current=current, revisions=[newest])

    newer = newest
    for version in range(current - 1, max(0, current - limit), -1):
        try:
            document = _fetch(metadata_url, version, timeout)
        except MetadataUnavailableError as exc:
            history.message = f"History stops here: {exc}"
            break
        except RepositoryError as exc:
            history.message = (
                f"Version {version} of root could not be read: {exc}"
            )
            break

        # The file has to be the version that was asked for. A server that
        # answers 3.root.json with version 7 would pass every signature
        # check, since the document is genuine, while the rotations were
        # then checked against the wrong pairs.
        if document.signed.version != version:
            history.message = (
                f"Version {version} of root answered with version "
                f"{document.signed.version}, so the history stops here"
            )
            break

        older = RootRevision(
            version=document.signed.version,
            expires=document.signed.expires,
            document=document,
            by_own_keys=_check(document.signed, document),
        )

        # The older version is what authorises the rotation into the newer
        # one, so the older version is what performs that check.
        newer.by_previous_keys = _check(document.signed, newer.document)
        newer.note = newer.note or _rotation_note(newer, older)

        if not older.by_own_keys.verified:
            older.note = (
                f"version {older.version} carries "
                f"{older.by_own_keys.present} of the "
                f"{older.by_own_keys.threshold} signatures it requires"
            )

        history.revisions.append(older)
        newer = older

    if history.message is None and history.earliest > 1:
        history.message = (
            f"Showing versions {history.earliest} to {current}. "
            "Earlier versions exist and were not fetched."
        )

    return history


async def load_root_history(
    metadata_url: str,
    trusted: Metadata,
    limit: int = DEFAULT_HISTORY,
    timeout: float = 10.0,
) -> RootHistory:
    """Read root's history, off the event loop."""
    limit = max(1, min(limit, MAX_HISTORY))
    return await asyncio.to_thread(
        _walk, metadata_url, trusted, limit, timeout
    )
