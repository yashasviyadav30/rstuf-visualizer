# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Short-lived reuse of built responses.

The cache exists to spare the storage server, not to hide the repository's
current state: entries live for seconds, and asking explicitly clears them.

Callers see two methods, ``get_or_build`` and ``clear``. Nothing else is
exposed, so replacing this with a shared store such as Redis is a change to
one file.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any


class TTLCache:
    """An in-process cache where each key refreshes at most once at a time.

    Without the per-key lock, a cache miss under load lets every waiting
    request rebuild the same entry: the storage server sees a burst instead
    of one fetch, and two refreshes can write the trust directory at the same
    moment. The lock lets the first caller build while the rest wait for its
    result.
    """

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _fresh(self, key: str) -> tuple[bool, Any]:
        entry = self._entries.get(key)
        if entry is None:
            return False, None
        stored_at, value = entry
        if (time.monotonic() - stored_at) >= self._ttl:
            return False, None
        return True, value

    def _prune(self) -> None:
        """Drop what has gone stale, so the process does not grow.

        Keys carry the version they describe, and a repository issues a new
        version every time its worker renews a role. Without this, a service
        left running would hold one entry for every version it ever saw.

        Locks go with their entries, but only the ones nobody holds. A caller
        takes a lock with no await between reaching for it and entering it,
        so an unlocked lock has no waiter left to strand.
        """
        now = time.monotonic()
        for key in [
            key
            for key, (stored_at, _) in self._entries.items()
            if (now - stored_at) >= self._ttl
        ]:
            del self._entries[key]

        for key, lock in list(self._locks.items()):
            if key not in self._entries and not lock.locked():
                del self._locks[key]

    async def get_or_build(
        self, key: str, build: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Return the cached value for ``key``, building it if needed."""
        self._prune()

        hit, value = self._fresh(key)
        if hit:
            return value

        # Created lazily because a lock must belong to a running event loop.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Another caller may have finished while this one waited.
            hit, value = self._fresh(key)
            if hit:
                return value

            value = await build()
            self._entries[key] = (time.monotonic(), value)
            return value

    def clear(self) -> None:
        """Drop every entry, so the next request goes to the repository."""
        self._entries.clear()
        for key, lock in list(self._locks.items()):
            if not lock.locked():
                del self._locks[key]
