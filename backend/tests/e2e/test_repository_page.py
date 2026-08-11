# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What a person actually sees.

Every other test in this suite can pass while the screen stays blank. A
response carrying the right fields is not a table anyone can read, and this is
the only layer that knows the difference.
"""

from __future__ import annotations

import pytest

from tests.base import BrowserTestCase

# Imported through pytest so a checkout without the development dependencies
# skips these with a reason, rather than failing to collect at all.
sync_api = pytest.importorskip(
    "playwright.sync_api",
    reason="pytest-playwright is a development dependency; run `make setup`",
)
Page = sync_api.Page
expect = sync_api.expect


class TestAHealthyRepository(BrowserTestCase):
    def test_reports_the_repository_as_healthy(
        self, page: Page, visualizer_url
    ) -> None:
        """The badge stays green while timestamp is inside a day of expiring.

        That is the normal state of a working repository, and it is the whole
        reason the badge no longer shows the worst band it can find.
        """
        page.goto(visualizer_url("good"))

        expect(page.get_by_text("All healthy")).to_be_visible()

    def test_lists_every_top_level_role(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        table = page.locator("table.table").first

        for role in ("root", "timestamp", "snapshot", "targets"):
            expect(table.get_by_text(role, exact=True)).to_be_visible()

    def test_draws_the_delegation_tree(
        self, page: Page, visualizer_url
    ) -> None:
        """The tree is computed from the metadata, so it has to be drawn to
        know the computing worked."""
        page.goto(visualizer_url("good"))

        expect(page.get_by_role("img", name="Delegation tree")).to_be_visible()
        expect(page.get_by_text("2 delegated roles")).to_be_visible()

    def test_opens_one_role_without_leaving_the_page(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("button", name="targets", exact=True).click()

        detail = page.locator(".detail")
        expect(detail.get_by_role("heading", name="targets")).to_be_visible()
        expect(detail.get_by_text("Download the signed file")).to_be_visible()

    def test_says_how_old_the_reading_is(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))

        expect(page.get_by_text("checked", exact=False)).to_be_visible()


class TestArtifacts(BrowserTestCase):
    """The screen opens as counts, not as every package ever carried."""

    def test_opens_as_a_list_of_bins_with_counts(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("button", name="Artifacts").click()

        expect(page.get_by_text("bins-0")).to_be_visible()
        expect(page.get_by_text("bins-1")).to_be_visible()
        # Nothing is read until a bin is opened, which is what keeps a
        # repository of two hundred and fifty-six bins cheap to look at.
        expect(
            page.get_by_text("Open a bin, or search across all of them.")
        ).to_be_visible()

    def test_opening_a_bin_lists_what_it_holds(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("button", name="Artifacts").click()
        page.get_by_role("button", name="bins-0", exact=False).click()

        rows = page.locator("table.table tbody tr")
        expect(rows.first).to_be_visible()
        assert rows.count() > 0


class TestABrokenRepository(BrowserTestCase):
    """Showing broken trust is the point, so it must reach the screen."""

    def test_an_expired_repository_says_so(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("expired"))

        expect(page.get_by_text("Verification stopped.")).to_be_visible()
        expect(page.get_by_text("expired", exact=False).first).to_be_visible()

    def test_a_tampered_repository_names_the_shortfall(
        self, page: Page, visualizer_url
    ) -> None:
        """`targets was signed by 0/1 keys` is the message that matters: it
        says which role fell short and by how much."""
        page.goto(visualizer_url("tampered"))

        expect(page.get_by_text("Verification stopped.")).to_be_visible()
        expect(page.get_by_text("signed by", exact=False)).to_be_visible()
