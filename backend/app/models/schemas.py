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


class RepositoryState(str, Enum):
    """How far the repository has progressed through initialisation."""

    READY = "ready"
    NOT_INITIALISED = "not_initialised"
    INITIALISING = "initialising"
    AWAITING_SIGNATURES = "awaiting_signatures"


class RoleSummary(BaseModel):
    """One node of the delegation tree."""

    name: str
    version: int
    expires: str = Field(description="ISO-8601 expiry timestamp")
    threshold: int | None = Field(
        default=None,
        description="Signatures required, when declared by a parent",
    )
    key_count: int | None = Field(
        default=None, description="Keys authorised to sign this role"
    )
    status: RoleStatus = RoleStatus.UNKNOWN


class TreeEdge(BaseModel):
    """A delegation from one role to another."""

    parent: str
    child: str


class OverviewResponse(BaseModel):
    """Everything the initial page render needs."""

    state: RepositoryState
    roles: list[RoleSummary] = Field(default_factory=list)
    edges: list[TreeEdge] = Field(default_factory=list)
    message: str | None = Field(
        default=None, description="Explanation shown when no tree is available"
    )
