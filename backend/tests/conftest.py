# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Shared fixtures for the test suite."""

from __future__ import annotations

import base64
import functools
import http.server
import importlib.util
import json
import os
import socketserver
import tempfile
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services.visualizer_service import VisualizerService, get_service

BACKEND_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = BACKEND_ROOT / "fixtures"
GENERATOR = BACKEND_ROOT / "scripts" / "gen_fixture.py"


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


def _fixtures_are_usable() -> bool:
    """Report whether the generated repositories are present and in date.

    The valid repository carries a short-lived timestamp, matching how RSTUF
    renews that role. Left alone it lapses within a day, which would fail the
    suite for a reason that says nothing about the code, so freshness is
    checked rather than assumed.
    """
    timestamp = FIXTURE_ROOT / "good" / "timestamp.json"
    if not timestamp.exists():
        return False

    try:
        document = json.loads(timestamp.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(document["signed"]["expires"])
    except (OSError, ValueError, KeyError):
        return False

    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


@pytest.fixture(scope="session", autouse=True)
def generated_repositories() -> None:
    """Rebuild the local repositories when they are missing or out of date."""
    if _fixtures_are_usable() or not GENERATOR.exists():
        return

    spec = importlib.util.spec_from_file_location("gen_fixture", GENERATOR)
    if spec is None or spec.loader is None:  # pragma: no cover
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


requires_symlinks = pytest.mark.skipif(
    not symlinks_permitted(),
    reason=(
        "the TUF client requires symbolic links; "
        "enable Developer Mode on Windows"
    ),
)

requires_fixtures = pytest.mark.skipif(
    not GENERATOR.exists(),
    reason="scripts/gen_fixture.py is required to build test repositories",
)


class _ReusableServer(socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture
def serve_directory() -> Iterator[object]:
    """Serve any directory of metadata over HTTP and yield its base URL."""
    servers: list[socketserver.TCPServer] = []

    def _serve(directory: str | Path) -> str:
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
def serve_fixture(serve_directory) -> object:
    """Serve one of the generated repositories and yield its base URL."""

    def _serve(variant: str) -> str:
        return serve_directory(FIXTURE_ROOT / variant)

    return _serve


@pytest.fixture
def bootstrap_root() -> object:
    """Return the trust anchor bytes for a generated repository."""

    def _read(variant: str) -> bytes:
        return (FIXTURE_ROOT / variant / "root.json").read_bytes()

    return _read


@pytest.fixture
def visualizer(tmp_path: Path, serve_fixture) -> Iterator[object]:
    """Return an HTTP client wired to one of the generated repositories.

    Each test gets its own trust directory, so one test's verified files
    cannot decide another test's result.
    """

    def _client(variant: str) -> TestClient:
        anchor = (FIXTURE_ROOT / variant / "root.json").read_bytes()
        settings = Settings(
            metadata_url=serve_fixture(variant),
            trusted_root=base64.b64encode(anchor).decode(),
            api_url=None,
        )
        service = VisualizerService(settings)
        service._trust_dir = tmp_path / variant
        app.dependency_overrides[get_service] = lambda: service
        return TestClient(app)

    yield _client

    app.dependency_overrides.clear()
