# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What a person actually sees.

Every other test in this suite can pass while the screen stays blank. A
response carrying the right fields is not a table anyone can read, and this is
the only layer that knows the difference.
"""

from __future__ import annotations

import re

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

        expect(
            page.get_by_role("group", name="Delegation tree")
        ).to_be_visible()
        expect(page.get_by_text("2 delegated roles")).to_be_visible()

    def test_a_bin_can_be_opened_without_a_mouse(
        self, page: Page, visualizer_url
    ) -> None:
        """Every top-level role is a row in the table as well, but a
        delegated one is only reachable in the tree. If the tree needs a
        mouse, those roles cannot be opened at all."""
        page.goto(visualizer_url("good"))

        page.get_by_role("button", name="Show 2 delegated roles").focus()
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Open bins-0").focus()
        page.keyboard.press("Enter")

        detail = page.locator(".detail")
        expect(detail.get_by_role("heading", name="bins-0")).to_be_visible()

    def test_opens_one_role_without_leaving_the_page(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("button", name="targets", exact=True).click()

        detail = page.locator(".detail")
        expect(detail.get_by_role("heading", name="targets")).to_be_visible()
        expect(detail.get_by_text("Download the signed file")).to_be_visible()

    def test_refresh_asks_the_backend_to_check_the_repository(
        self, page: Page, visualizer_url
    ) -> None:
        """The button has one job, and it is that query parameter.

        Without it the backend serves the reading it already holds, the
        screen redraws identically, and the rate limit that decides whether
        a second look is worth taking is never reached.
        """
        asked: list[str] = []
        page.on(
            "request",
            lambda request: (
                asked.append(request.url)
                if "/api/v1/overview" in request.url
                else None
            ),
        )

        page.goto(visualizer_url("good"))
        expect(page.get_by_text("All healthy")).to_be_visible()
        assert asked, "the page never asked for an overview"
        assert (
            "refresh=true" not in asked[0]
        ), "the first read is not a refresh"

        with page.expect_request(
            lambda r: "refresh=true" in r.url, timeout=10000
        ):
            page.get_by_role("button", name="Refresh").click()

    def test_says_how_old_the_reading_is(
        self, page: Page, visualizer_url
    ) -> None:
        """In words, and as a whole sentence.

        "checked 0 seconds" is not what anybody says. The point of the label
        is to answer, without a click, whether the screen is current.
        """
        page.goto(visualizer_url("good"))

        expect(page.get_by_text("seconds ago", exact=False)).to_be_visible()


class TestArtifacts(BrowserTestCase):
    """The screen opens as counts, not as every package ever carried."""

    def test_opens_as_a_list_of_bins_with_counts(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Artifacts").click()

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
        page.get_by_role("link", name="Artifacts").click()
        page.get_by_role("button", name="bins-0", exact=False).click()

        rows = page.locator("table.table tbody tr")
        expect(rows.first).to_be_visible()
        assert rows.count() > 0


class TestRootHistory(BrowserTestCase):
    """The screen a signer uses to confirm a rotation went as intended."""

    def test_accuses_nothing_in_a_repository_that_verifies(
        self, page: Page, visualizer_url
    ) -> None:
        """No version of a sound root may be reported as unsigned.

        The checks arrive as objects carrying a count, not as flags. Read as
        flags they are always truthy, which reads as "signed" for a check that
        failed and, for the oldest version reached, as a failure where there
        was simply nothing above it to check against. On the one screen whose
        purpose is auditing rotations, that clears a broken root and accuses a
        sound one.
        """
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Root history").click()

        expect(page.get_by_text("How root reached version 3")).to_be_visible()
        expect(page.get_by_text("NOT signed by")).to_have_count(0)

    def test_shows_the_numbers_behind_each_check(
        self, page: Page, visualizer_url
    ) -> None:
        """A verdict without its count is not evidence.

        This repository rotated from a root holding one key to one holding
        two, which is the change the screen exists to make visible: version 1
        signs with one key, versions 2 and 3 with two.
        """
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Root history").click()

        expect(
            page.get_by_text("signed by its own keys (1 of 1)")
        ).to_have_count(1)
        expect(
            page.get_by_text("signed by its own keys (2 of 2)")
        ).to_have_count(2)

    def test_says_when_there_was_no_earlier_version_to_check(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Root history").click()

        expect(page.get_by_text("no earlier version was read")).to_be_visible()


class TestAddresses(BrowserTestCase):
    """Each screen has an address that can be copied, sent and reopened."""

    def test_a_screen_can_be_opened_directly(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(f"{visualizer_url('good')}/#/roots")

        expect(page.get_by_text("How root reached version 3")).to_be_visible()

    def test_the_address_follows_the_screen(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Artifacts").click()

        expect(page).to_have_url(re.compile(r"#/artifacts$"))

    def test_an_address_nobody_published_still_answers(
        self, page: Page, visualizer_url
    ) -> None:
        page.goto(f"{visualizer_url('good')}/#/no-such-screen")

        expect(page.get_by_text("No such screen")).to_be_visible()
        # The header belongs to every screen, including this one.
        expect(page.get_by_text("All healthy")).to_be_visible()


class TestStatus(BrowserTestCase):
    def test_says_plainly_when_no_api_is_configured(
        self, page: Page, visualizer_url
    ) -> None:
        """The repository is read and verified without it, because none of
        the trust picture comes from there."""
        page.goto(visualizer_url("good"))
        page.get_by_role("link", name="Status").click()

        expect(
            page.get_by_text("No RSTUF API is configured", exact=False)
        ).to_be_visible()


class TestRoleDetail(BrowserTestCase):
    def test_counts_the_signatures_on_a_top_level_role(
        self, page: Page, visualizer_url
    ) -> None:
        """An operator reading a signature count is asking about evidence,
        and the honest answer to "how many" is never "enough"."""
        page.goto(visualizer_url("good"))
        page.get_by_role("button", name="root", exact=True).click()

        expect(
            page.locator(".detail").get_by_text("2 of 2 required")
        ).to_be_visible()


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
