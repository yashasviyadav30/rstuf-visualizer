# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""A running service for a browser to talk to.

The rest of the suite drives the application in-process, which is faster and
enough to know what it answers. A browser cannot do that: it needs a port. So
these tests start the real application on one, serving the compiled interface
exactly as the container does.
"""

from __future__ import annotations

import base64
import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from app.config import get_settings
from app.main import create_app
from app.services.metadata_service import get_metadata_service
from tests.conftest import FIXTURE_ROOT


def _free_port() -> int:
    """Ask the operating system for a port nobody is using."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def visualizer_url(monkeypatch, serve_fixture) -> Iterator[object]:
    """Start the service against one generated repository, and yield its URL.

    Configuration arrives through the environment, never through an
    override, because this is the real application: it reads its settings the
    same way it does in the container, and both caches are cleared so it reads
    them again instead of reusing a previous test's.
    """
    servers: list[uvicorn.Server] = []
    threads: list[threading.Thread] = []

    def _start(variant: str) -> str:
        anchor = (FIXTURE_ROOT / variant / "root.json").read_bytes()
        monkeypatch.setenv("RSTUF_METADATA_URL", serve_fixture(variant))
        monkeypatch.setenv(
            "RSTUF_TRUSTED_ROOT", base64.b64encode(anchor).decode()
        )
        monkeypatch.delenv("RSTUF_API_URL", raising=False)
        get_settings.cache_clear()
        get_metadata_service.cache_clear()

        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(),
                host="127.0.0.1",
                port=port,
                log_level="warning",
            )
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        servers.append(server)
        threads.append(thread)

        deadline = time.monotonic() + 20
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("the service did not start")
            time.sleep(0.05)

        return f"http://127.0.0.1:{port}"

    yield _start

    for server in servers:
        server.should_exit = True
    for thread in threads:
        thread.join(timeout=10)

    get_settings.cache_clear()
    get_metadata_service.cache_clear()
