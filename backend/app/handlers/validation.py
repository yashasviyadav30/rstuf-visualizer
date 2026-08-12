# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Patterns applied to values arriving from the browser.

Held apart from the handlers because more than one of them narrows by role,
and a rule enforced in two places eventually stops matching itself.
"""

# A role name reaches us in a URL and is used to build a filename, so it is
# constrained here and never trusted. This also rejects path traversal
# before any of our own code runs.
ROLE_NAME = r"^[A-Za-z0-9._-]{1,128}$"

# The same name, or nothing at all. Used where narrowing to a role is optional
# and an empty value means "every role", which the pattern above would reject.
OPTIONAL_ROLE_NAME = r"^$|^[A-Za-z0-9._-]{1,128}$"
