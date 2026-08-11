# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What a failure looks like, declared so a consumer can read it.

Every route here can fail in a small number of ways, and each failure
carries a message written for a person. Declaring them puts those shapes in
the OpenAPI document, which is what the interface generates its types from:
undeclared, the error path is the one part of the contract a consumer has to
guess at, and the error path is most of what this service exists to report.

The codes follow one rule. Broken trust is the subject of this service, so an
expired or badly signed repository is a normal answer carrying a status, not
a failure. A request for something that does not exist is the caller's
mistake. Only a repository that cannot be reached, or one that cannot be
checked at all, is reported as a failure of the service.
"""

from __future__ import annotations

from typing import Any

from app.dto.schemas import ErrorResponse

_UNREACHABLE = {
    "model": ErrorResponse,
    "description": (
        "The repository could not be read. Its metadata server did not "
        "answer, so there is nothing to show"
    ),
}

_UNVERIFIABLE = {
    "model": ErrorResponse,
    "description": (
        "Nothing can be checked. No trust anchor is available, and showing "
        "metadata that has not been verified would state a falsehood "
        "confidently"
    ),
}

_UNKNOWN_ROLE = {
    "model": ErrorResponse,
    "description": "This repository does not delegate to a role by that name",
}

#: For routes that read the repository.
REPOSITORY: dict[int | str, dict[str, Any]] = {
    502: _UNREACHABLE,
    503: _UNVERIFIABLE,
}

#: For routes that read one named role.
ROLE: dict[int | str, dict[str, Any]] = {
    404: _UNKNOWN_ROLE,
    502: _UNREACHABLE,
    503: _UNVERIFIABLE,
}
