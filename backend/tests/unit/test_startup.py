# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""What happens to a deployment that is missing a setting."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import get_settings
from app.main import create_app
from tests.base import UnitTestCase


class TestStartup(UnitTestCase):
    """Settings are read once, while the server starts.

    A server whose startup raises exits instead of serving. Left until the
    first request, a missing setting would pass every health check and fail
    every real request, which reads as a broken repository and not a broken
    deployment.
    """

    @pytest.fixture(autouse=True)
    def _unread_settings(self):
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_a_missing_metadata_url_stops_the_server(self, monkeypatch):
        monkeypatch.delenv("RSTUF_METADATA_URL", raising=False)

        with pytest.raises(ValidationError, match="metadata_url"):
            with TestClient(create_app()):
                pass

    def test_a_configured_deployment_starts(self, monkeypatch) -> None:
        monkeypatch.setenv("RSTUF_METADATA_URL", "http://metadata.example/")

        with TestClient(create_app()) as client:
            assert client.get("/healthz").status_code == 200
