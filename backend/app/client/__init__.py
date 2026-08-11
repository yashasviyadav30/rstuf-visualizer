# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Connections to the two things outside this process.

The TUF client, which fetches and verifies signed metadata, and the RSTUF
API, which answers questions the metadata cannot. Both are configured here
and called from elsewhere.
"""
