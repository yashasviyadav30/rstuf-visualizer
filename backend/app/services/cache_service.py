# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Short-lived reuse of built responses.

The cache spares the storage server; it is not there to hide the state of the
repository. Entries live for seconds and asking explicitly clears them.

Three methods are exposed, so putting a shared store such as Redis behind
them is a change to one file.
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
    of one fetch, and two refreshes write the trust directory at the same
    moment. The first caller builds; the rest wait for its result.
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

    def age(self, key: str) -> float | None:
        """Seconds since ``key`` was stored, or ``None`` if it is not held.

        A refresh is worth honouring only when the answer in hand is old
        enough that a new one could differ, and this is how that is decided.
        The page reports its own age from the reading itself, not from here.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        return time.monotonic() - entry[0]

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
