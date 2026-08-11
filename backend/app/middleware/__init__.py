# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What every request passes through, whichever handler answers it.

This is the layer that makes the service extensible in the direction it was
asked to grow. Authentication and per-role permissions belong here, in front
of the handlers, so neither the metadata layer nor any route has to learn who
is asking.
"""
