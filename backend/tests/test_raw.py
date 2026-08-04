# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for serving the bytes a role was verified from.

The link on a role's detail panel points here rather than at the storage the
files came from, so what a reader opens is the document the page describes.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.service import VisualizerService, get_service
from tests.conftest import FIXTURE_ROOT, requires_fixtures, requires_symlinks


@pytest.fixture
def visualizer(tmp_path: Path, serve_fixture) -> Iterator[object]:
    """Return a client wired to one of the generated repositories."""

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


@requires_fixtures
@requires_symlinks
class TestRawMetadata:
    def test_the_detail_panel_says_where_to_read_the_bytes(
        self, visualizer
    ) -> None:
        body = visualizer("good").get("/api/v1/roles/root").json()

        assert body["raw_url"] == "/api/v1/roles/root/raw"

    def test_serves_a_top_level_role_from_what_was_verified(
        self, visualizer
    ) -> None:
        client = visualizer("good")
        described = client.get("/api/v1/roles/targets").json()

        response = client.get(described["raw_url"])
        document = json.loads(response.content)

        assert response.status_code == 200
        # The same version the page reported, not a later fetch of the file.
        assert document["signed"]["version"] == described["version"]
        assert document["signed"]["_type"] == "targets"

    def test_serves_a_delegated_role_it_checked_on_request(
        self, visualizer
    ) -> None:
        client = visualizer("good")
        described = client.get("/api/v1/roles/bins-0").json()

        document = json.loads(client.get(described["raw_url"]).content)

        assert document["signed"]["version"] == described["version"]
        assert set(document) == {"signed", "signatures"}

    def test_serves_the_root_the_client_settled_on(self, visualizer) -> None:
        """The anchor handed over is version one; the chain ends at three.
        What is served is what the client accepted, not what it started with.
        """
        document = json.loads(
            visualizer("good").get("/api/v1/roles/root/raw").content
        )

        assert document["signed"]["version"] == 3

    def test_hands_the_file_over_rather_than_rendering_it(
        self, visualizer
    ) -> None:
        """Metadata comes from a repository this service does not control, so
        it is never returned as something a browser will execute."""
        response = visualizer("good").get("/api/v1/roles/root/raw")

        assert response.headers["content-type"].startswith("application/json")
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["x-content-type-options"] == "nosniff"

    def test_answers_an_unknown_role_as_unknown(self, visualizer) -> None:
        response = visualizer("good").get("/api/v1/roles/nope/raw")

        assert response.status_code == 404

    def test_rejects_a_name_that_is_not_a_role_name(self, visualizer) -> None:
        response = visualizer("good").get("/api/v1/roles/..%2Froot/raw")

        assert response.status_code in (404, 422)
