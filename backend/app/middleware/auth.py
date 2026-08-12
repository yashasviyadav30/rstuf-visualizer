# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Where authentication will attach. Nothing is enforced today.

This service is read-only and unauthenticated, like the repository it
displays: the signed metadata is published, so there is nothing here to keep
from a visitor. This module says so, because an empty folder would leave a
reader guessing whether the check was forgotten.

Write access changes that. RSTUF is being evaluated for package indexes where
separate teams own separate paths and hold their own online keys, and adding
a delegation, rotating a key or deciding who may do either are all requests
that have to know who is asking.

The seam sits in front of the handlers because every request already passes
one door. When it lands, ``require_caller`` becomes a dependency on the
routes that change something, and the metadata layer below never learns that
callers exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    """Whoever made the request.

    Anonymous today, since nothing distinguishes one reader from another.
    """

    name: str = "anonymous"
    roles: frozenset[str] = frozenset()
    """Which roles this caller may act on. Empty is not "all of them"."""


def current_caller() -> Caller:
    """Identify the caller.

    Returns the anonymous caller, always. A real implementation reads a
    credential from the request and fails the request when it is absent or
    invalid; until write operations exist there is no request to fail.
    """
    return Caller()
