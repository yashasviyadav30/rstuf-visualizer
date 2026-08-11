# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Where authentication will attach. Nothing is enforced today.

This service is read-only and unauthenticated, like the repository it
displays: the signed metadata is published, so there is nothing here to keep
from a visitor. Saying that plainly is the point of this module. An empty
folder would leave a reader guessing whether the check was forgotten.

What changes that is write access. RSTUF is being evaluated for package
indexes where separate teams own separate paths and hold their own online
keys, and the operations they need are adding a delegation, rotating a key,
and deciding who may do either. Those are the requests that have to know who
is asking.

The seam is here rather than in the handlers because every request already
passes one door, and per-role permissions are a question about the caller,
not about the metadata. When it lands, ``require_caller`` becomes a
dependency on the routes that change something, and the metadata layer below
never learns that callers exist.
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

    @property
    def is_anonymous(self) -> bool:
        return self.name == "anonymous"


def current_caller() -> Caller:
    """Identify the caller.

    Returns the anonymous caller, always. A real implementation reads a
    credential from the request and fails the request when it is absent or
    invalid; until write operations exist there is no request to fail.
    """
    return Caller()
