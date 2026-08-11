# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Reaching the API from a frontend served somewhere else."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

DEV_SERVER = "http://localhost:5173"
ALLOW_ORIGIN = "access-control-allow-origin"


def _client(monkeypatch, origins: str) -> TestClient:
    monkeypatch.setenv("RSTUF_CORS_ORIGINS", origins)
    return TestClient(create_app())


class TestCrossOriginAccess:
    """The shipped arrangement needs none of this.

    The interface is served from the same process as the API, so a browser
    asks one origin for both. A frontend development server does not: it
    answers on a port of its own, which the browser treats as another site.
    """

    def test_allows_an_origin_a_deployment_named(self, monkeypatch) -> None:
        client = _client(monkeypatch, DEV_SERVER)
        response = client.get("/healthz", headers={"Origin": DEV_SERVER})

        assert response.headers[ALLOW_ORIGIN] == DEV_SERVER

    def test_refuses_an_origin_nobody_named(self, monkeypatch) -> None:
        """Naming one origin is not the same as opening the door."""
        client = _client(monkeypatch, DEV_SERVER)
        response = client.get(
            "/healthz", headers={"Origin": "http://elsewhere.example"}
        )

        assert ALLOW_ORIGIN not in response.headers

    def test_grants_nothing_by_default(self, monkeypatch) -> None:
        """Unset means the middleware is never attached at all."""
        client = _client(monkeypatch, "")
        response = client.get("/healthz", headers={"Origin": DEV_SERVER})

        assert ALLOW_ORIGIN not in response.headers

    def test_reads_a_list(self, monkeypatch) -> None:
        client = _client(monkeypatch, f"{DEV_SERVER}, http://127.0.0.1:3000")
        response = client.get(
            "/healthz", headers={"Origin": "http://127.0.0.1:3000"}
        )

        assert response.headers[ALLOW_ORIGIN] == "http://127.0.0.1:3000"
