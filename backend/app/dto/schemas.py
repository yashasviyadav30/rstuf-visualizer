# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Response shapes returned to the browser.

These are deliberately narrower than the underlying TUF metadata. The browser
depends on this contract rather than on the library's internals, so the
metadata format can change without breaking the interface.
"""

from enum import Enum

from pydantic import BaseModel, Field


class RoleStatus(str, Enum):
    """Outcome of verifying one role."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class ExpiryBand(str, Enum):
    """How close a role is to expiring.

    Valid and expired alone hide the difference that matters. Timestamp is
    renewed roughly daily, so in normal operation it sits in ``CRITICAL``;
    calling that plain ``VALID`` until the moment it lapses discards the only
    useful warning.
    """

    EXPIRED = "expired"
    CRITICAL = "critical"
    EXPIRING = "expiring"
    VALID = "valid"


class RepositoryState(str, Enum):
    """How far the repository has progressed through initialisation."""

    READY = "ready"
    NOT_INITIALISED = "not_initialised"
    INITIALISING = "initialising"
    AWAITING_SIGNATURES = "awaiting_signatures"


class ErrorResponse(BaseModel):
    """What every failure from this API carries.

    The shape FastAPI sends for an HTTPException, named here so it appears in
    the OpenAPI document rather than being left for a consumer to discover.
    The message is written for a person to read.
    """

    detail: str = Field(
        description="Why the request could not be answered",
        examples=["This repository does not delegate to a role named bins-99"],
    )


class KeySummary(BaseModel):
    """One signing key, named rather than shown as a bare identifier."""

    keyid: str = Field(description="Full key identifier")
    keyid_short: str = Field(description="First 8 characters, for display")
    name: str = Field(description="Readable name, or the short identifier")
    scheme: str = ""
    online: bool = Field(
        default=False,
        description="True when RSTUF records an online key URI for it",
    )
    signs: list[str] = Field(
        default_factory=list, description="Roles this key is authorised for"
    )


class RoleSummary(BaseModel):
    """One verified role, as shown in the table and the tree."""

    name: str
    version: int
    expires: str = Field(description="ISO-8601 expiry timestamp")
    expires_in: str = Field(
        default="", description="Readable distance to expiry"
    )
    band: ExpiryBand = ExpiryBand.VALID
    threshold: int | None = Field(
        default=None,
        description="Signatures required, when declared by a parent",
    )
    key_count: int | None = Field(
        default=None, description="Keys authorised to sign this role"
    )
    key_names: list[str] = Field(default_factory=list)
    status: RoleStatus = RoleStatus.UNKNOWN


class DelegatedSummary(BaseModel):
    """A delegated role that has not been fetched.

    Its name comes from the delegation rule and its version from snapshot, so
    both are known without downloading the file. Everything else waits until
    somebody opens it.
    """

    name: str
    version: int | None = None
    loaded: bool = False


class TreeEdge(BaseModel):
    """A delegation from one role to another."""

    parent: str
    child: str


class ArtifactSummary(BaseModel):
    """One artifact listed by a delegated role."""

    path: str
    length: int
    hashes: dict[str, str] = Field(default_factory=dict)
    role: str = Field(description="The delegated role listing it")


class OverviewResponse(BaseModel):
    """Everything the initial page render needs."""

    state: RepositoryState
    status: RoleStatus = RoleStatus.UNKNOWN
    checked_at: str = Field(default="", description="When this was verified")
    roles: list[RoleSummary] = Field(default_factory=list)
    delegated: list[DelegatedSummary] = Field(
        default_factory=list,
        description="Delegated roles, named but not yet fetched",
    )
    edges: list[TreeEdge] = Field(default_factory=list)
    verification_error: str | None = Field(
        default=None, description="Why verification stopped, when it did"
    )
    message: str | None = Field(
        default=None, description="Explanation shown when no tree is available"
    )


class RoleDetailResponse(BaseModel):
    """One role, opened."""

    name: str
    version: int
    expires: str
    expires_in: str = ""
    band: ExpiryBand = ExpiryBand.VALID
    status: RoleStatus = RoleStatus.UNKNOWN
    threshold: int | None = None
    signed_by: list[KeySummary] = Field(default_factory=list)
    signatures_present: int | None = Field(
        default=None, description="Valid signatures found on this role"
    )
    signature_note: str | None = Field(
        default=None, description="Stated when a role is short of signatures"
    )
    delegates_to: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    raw_url: str = Field(
        default="",
        description=(
            "Where to read the bytes this role was verified from, served by "
            "this service rather than linked to the storage behind it"
        ),
    )


class ArtifactsResponse(BaseModel):
    """A page of artifacts, gathered from delegated roles."""

    total: int
    page: int
    page_size: int
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    unavailable: list[str] = Field(
        default_factory=list,
        description=(
            "Delegated roles that could not be read. Whatever they list is "
            "missing from this page, and from the total beside it, so the "
            "shortfall is named rather than left to look like an empty bin"
        ),
    )


class BinSummary(BaseModel):
    """One role that holds artifacts, and how many it holds."""

    name: str
    count: int
    available: bool = Field(
        default=True,
        description=(
            "False when the role could not be read. Its count is then 0, "
            "which is not the same as the role being empty"
        ),
    )


class ArtifactBinsResponse(BaseModel):
    """Every role holding artifacts, so the browser can open one at a time.

    The interface asks for this before it asks for artifacts, which is what
    keeps a repository of two hundred bins from sending two hundred bins to
    draw one screen.
    """

    total: int
    bins: list[BinSummary] = Field(default_factory=list)


class StatusResponse(BaseModel):
    """Live repository status, taken from the RSTUF API."""

    available: bool = Field(
        default=False, description="False when the RSTUF API cannot be reached"
    )
    state: RepositoryState = RepositoryState.NOT_INITIALISED
    bootstrap: str | None = None
    awaiting_signatures: list[str] = Field(default_factory=list)
    keys: list[KeySummary] = Field(default_factory=list)
    message: str | None = None


class KeyChangeAction(str, Enum):
    """What a rotation did to one key."""

    ADDED = "added"
    REMOVED = "removed"


class SignatureCheckSummary(BaseModel):
    """One threshold check, reported with the numbers behind it."""

    verified: bool
    present: int = Field(description="Valid signatures found")
    threshold: int = Field(description="Valid signatures required")


class RootKeyChange(BaseModel):
    """One key a rotation introduced or withdrew.

    A key identifier is derived from the key itself, so editing a key
    produces a new identifier. Altering a key therefore appears here as one
    removal and one addition, which is also how a verifier sees it.
    """

    keyid: str
    keyid_short: str
    name: str
    action: KeyChangeAction


class RootRoleChange(BaseModel):
    """How a rotation changed who may sign one role, and how many must."""

    role: str
    threshold_before: int | None = None
    threshold_after: int | None = None
    signers_added: list[str] = Field(default_factory=list)
    signers_removed: list[str] = Field(default_factory=list)


class RootVersionSummary(BaseModel):
    """One version of root, with what it changed and whether it checks out."""

    version: int
    expires: str
    expires_in: str = ""
    band: ExpiryBand | None = Field(
        default=None,
        description=(
            "How close this version is to expiring. Absent once a version "
            "has been superseded, because a client checks expiry only on "
            "the final root, so an old version lapsing means nothing"
        ),
    )
    superseded: bool = Field(
        default=False, description="True for every version but the current one"
    )
    verified: bool = Field(
        description="True when every check that applies to it passed"
    )
    by_own_keys: SignatureCheckSummary
    by_previous_keys: SignatureCheckSummary | None = Field(
        default=None,
        description="Absent for version one, and where the chain stops",
    )
    note: str | None = Field(
        default=None, description="Stated when a check did not pass"
    )
    key_count: int = 0
    keys_changed: list[RootKeyChange] = Field(default_factory=list)
    roles_changed: list[RootRoleChange] = Field(default_factory=list)


class RootsResponse(BaseModel):
    """Root's history, newest version first."""

    current: int = Field(description="The version in force now")
    earliest: int = Field(description="The oldest version read")
    versions: list[RootVersionSummary] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Stated when the history is partial, and why",
    )
