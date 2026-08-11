# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""The short-lived reuse of built responses."""

from __future__ import annotations

import asyncio

import pytest

from app.services.cache_service import TTLCache
from tests.base import UnitTestCase


class TestResponseCache(UnitTestCase):
    """The cache exists to spare the storage server, and to stop
    a burst of viewers turning into a burst of fetches.
    """

    @pytest.mark.asyncio
    async def test_reuses_a_value_within_its_lifetime(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        calls = 0

        async def build() -> str:
            nonlocal calls
            calls += 1
            return "built"

        assert await cache.get_or_build("k", build) == "built"
        assert await cache.get_or_build("k", build) == "built"
        assert calls == 1

    @pytest.mark.asyncio
    async def test_builds_again_once_the_entry_has_aged_out(self) -> None:
        cache = TTLCache(ttl_seconds=0.01)
        calls = 0

        async def build() -> int:
            nonlocal calls
            calls += 1
            return calls

        await cache.get_or_build("k", build)
        await asyncio.sleep(0.05)
        await cache.get_or_build("k", build)

        assert calls == 2

    @pytest.mark.asyncio
    async def test_clearing_forces_the_next_request_to_rebuild(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        calls = 0

        async def build() -> int:
            nonlocal calls
            calls += 1
            return calls

        await cache.get_or_build("k", build)
        cache.clear()
        await cache.get_or_build("k", build)

        assert calls == 2

    @pytest.mark.asyncio
    async def test_concurrent_misses_share_one_build(self) -> None:
        """Ten callers arriving together must cost one fetch, not ten.

        This is the property that keeps a burst of viewers from turning into a
        burst of requests against the storage server.
        """
        cache = TTLCache(ttl_seconds=60)
        calls = 0

        async def build() -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.02)
            return "built"

        results = await asyncio.gather(
            *(cache.get_or_build("k", build) for _ in range(10))
        )

        assert results == ["built"] * 10
        assert calls == 1

    @pytest.mark.asyncio
    async def test_separate_keys_do_not_block_each_other(self) -> None:
        cache = TTLCache(ttl_seconds=60)

        async def build_a() -> str:
            return "a"

        async def build_b() -> str:
            return "b"

        assert await cache.get_or_build("a", build_a) == "a"
        assert await cache.get_or_build("b", build_b) == "b"

    @pytest.mark.asyncio
    async def test_does_not_grow_as_versions_come_and_go(self) -> None:
        """Keys carry the version they describe, and RSTUF issues a
        new one every time its worker renews a role. A service left
        running for a week would otherwise hold a week of them.
        """
        cache = TTLCache(ttl_seconds=0)

        async def build() -> str:
            return "value"

        for version in range(50):
            await cache.get_or_build(f"artifacts:{version}", build)

        # Everything written has already outlived a zero-second
        # lifetime, so only the entry from this pass survives, and no
        # lock outlives its entry.
        assert len(cache._entries) <= 1
        assert len(cache._locks) <= 1

    @pytest.mark.asyncio
    async def test_keeps_a_lock_that_someone_is_holding(self) -> None:
        """Pruning must not take a lock out from under a caller mid-build."""
        cache = TTLCache(ttl_seconds=0)
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow() -> str:
            started.set()
            await release.wait()
            return "slow"

        async def quick() -> str:
            return "quick"

        task = asyncio.create_task(cache.get_or_build("shared", slow))
        await started.wait()

        # A second key going through prunes while the first is still building.
        await cache.get_or_build("other", quick)
        assert cache._locks["shared"].locked()

        release.set()
        assert await task == "slow"
