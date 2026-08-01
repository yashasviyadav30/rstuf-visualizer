# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for the operational endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_reports_ok() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_returns_404() -> None:
    response = client.get("/no-such-endpoint")

    assert response.status_code == 404
