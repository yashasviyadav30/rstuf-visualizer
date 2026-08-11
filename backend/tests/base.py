# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What the test classes inherit from.

Two kinds of test live in this suite, and what separates them is what each
one is allowed to touch.

A unit test touches nothing outside the process. It runs on any machine, in
under a second, and a failure names one module. Those live in ``tests/unit``.

An integration test drives a repository that was generated with real keys and
served over HTTP, and lets python-tuf verify it. That is the evidence this
service works at all, because a signature either checks out or it does not,
and no amount of mocking can tell you which. Those live in
``tests/integration``, and they carry the two conditions they depend on: the
generator that builds the repositories, and permission to create the symbolic
link python-tuf caches its trust anchor behind. Declaring both on a base
class rather than on each class means a new test cannot quietly forget one
and appear to pass.

An end-to-end test opens the built interface in a real browser, pointed at a
backend reading one of those repositories. It is the only layer that can tell
you the whole thing works: the API answering correctly proves nothing about
whether anything reached a screen. Those live in ``tests/e2e`` and need the
interface compiled first, which is a condition of their own.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    FRONTEND_DIST,
    requires_browser,
    requires_fixtures,
    requires_symlinks,
)


class UnitTestCase:
    """A test that reaches nothing outside this process.

    No network, no generated repository, no trust directory. Anything the
    module under test would normally call is replaced by the test.
    """


class RepositoryTestCase:
    """A test driven against a generated repository, through the API.

    Skips itself, with the reason stated, where the platform cannot support
    it. A green run that quietly omitted these would be worse than a red one.
    """

    pytestmark = [requires_fixtures, requires_symlinks]


requires_built_interface = pytest.mark.skipif(
    not (FRONTEND_DIST / "index.html").exists(),
    reason=(
        "the interface has to be compiled before a browser can open it; "
        "run `make build-frontend`"
    ),
)


class BrowserTestCase(RepositoryTestCase):
    """A test that opens the real page in a real browser.

    Everything below this can pass while the screen stays blank. A response
    with the right fields in it is not the same as a table a person can read,
    and this is the only layer that knows the difference.
    """

    pytestmark = [
        requires_fixtures,
        requires_symlinks,
        requires_built_interface,
        requires_browser,
    ]
