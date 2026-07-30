"""Shared fixtures for the test suite."""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def symlinks_permitted() -> bool:
    """Report whether this process may create symbolic links.

    python-tuf caches the trust anchor behind a symbolic link. Windows
    refuses that without Developer Mode or administrator rights, which makes
    the client unusable rather than merely degraded.
    """
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "target"
        target.write_text("", encoding="utf-8")
        try:
            os.symlink(target, Path(directory) / "link")
        except OSError:
            return False
        return True


requires_symlinks = pytest.mark.skipif(
    not symlinks_permitted(),
    reason="the TUF client requires symbolic links; enable Developer Mode on Windows",
)

requires_fixtures = pytest.mark.skipif(
    not (FIXTURE_ROOT / "good").exists(),
    reason="run scripts/gen_fixture.py to build the local test repositories",
)


class _ReusableServer(socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture
def serve_fixture() -> Iterator[object]:
    """Serve a generated repository over HTTP and yield its base URL."""
    servers: list[socketserver.TCPServer] = []

    def _serve(variant: str) -> str:
        directory = FIXTURE_ROOT / variant
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(directory)
        )
        server = _ReusableServer(("127.0.0.1", 0), handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}/"

    yield _serve

    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def bootstrap_root() -> object:
    """Return the trust anchor bytes for a generated repository."""

    def _read(variant: str) -> bytes:
        return (FIXTURE_ROOT / variant / "root.json").read_bytes()

    return _read
