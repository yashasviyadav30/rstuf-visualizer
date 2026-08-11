# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""The rules, and the ordering they impose.

One service holds what a request needs and decides what happens first; the
presenters turn verified metadata into the shapes above; the cache decides
what is worth reading again.
"""
