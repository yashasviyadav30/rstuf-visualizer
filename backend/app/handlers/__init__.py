# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""The HTTP surface, one module per subject.

Every route here is a GET. The visualizer reads a TUF repository and changes
nothing in it.

Answers follow one rule. Broken trust is the subject of this service, so an
expired or badly signed repository is a normal answer carrying a status. A
request for something that does not exist is the caller's mistake. Only a
repository that cannot be reached, or one that cannot be checked at all, is
reported as a failure of the service.

Handlers hold no rules of their own. Each one maps a request onto a service
call and maps the errors that call may raise onto status codes.
"""
