# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for turning verified metadata into browser responses."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.dto.schemas import ExpiryBand
from app.services.presenters import expiry_band
from tests.base import UnitTestCase

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def at(**delta: float) -> datetime:
    return NOW + timedelta(**delta)


class TestExpiryBand(UnitTestCase):
    def test_a_lapsed_role_is_expired(self) -> None:
        band, phrase = expiry_band(at(hours=-3), NOW)

        assert band is ExpiryBand.EXPIRED
        assert "ago" in phrase

    def test_under_a_day_is_critical(self) -> None:
        """Timestamp lives here in normal operation, so it must be its own
        band, and is not folded into 'valid'."""
        band, phrase = expiry_band(at(hours=5), NOW)

        assert band is ExpiryBand.CRITICAL
        assert "5h" in phrase

    def test_under_a_week_is_expiring(self) -> None:
        band, phrase = expiry_band(at(days=3), NOW)

        assert band is ExpiryBand.EXPIRING
        assert "3 days" in phrase

    def test_beyond_a_week_is_valid(self) -> None:
        band, _ = expiry_band(at(days=30), NOW)

        assert band is ExpiryBand.VALID

    def test_the_boundaries_fall_on_the_later_band(self) -> None:
        assert expiry_band(at(hours=24), NOW)[0] is ExpiryBand.EXPIRING
        assert expiry_band(at(days=7), NOW)[0] is ExpiryBand.VALID

    def test_a_distant_date_is_stated_rather_than_counted(self) -> None:
        _, phrase = expiry_band(at(days=400), NOW)

        assert "2027-" in phrase

    def test_a_naive_timestamp_is_read_as_utc(self) -> None:
        """Metadata carries UTC. Comparing a naive value would raise, so it
        is assumed, never rejected."""
        naive = at(days=30).replace(tzinfo=None)

        band, _ = expiry_band(naive, NOW)

        assert band is ExpiryBand.VALID

    def test_one_day_is_singular(self) -> None:
        _, phrase = expiry_band(at(days=1, hours=1), NOW)

        assert "1 day" in phrase and "1 days" not in phrase
