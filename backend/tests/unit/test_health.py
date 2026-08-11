# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""The operational endpoint, and what happens off the map."""

from fastapi.testclient import TestClient

from app.main import app
from tests.base import UnitTestCase

client = TestClient(app)


class TestLiveness(UnitTestCase):
    """A probe must answer whatever state the repository is in.

    This endpoint reports that the process is running and nothing else. A
    repository in trouble is what the service exists to show, so it must
    never be what takes the pod down.
    """

    def test_reports_ok(self) -> None:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_an_unknown_path_is_not_found(self) -> None:
        response = client.get("/no-such-endpoint")

        assert response.status_code == 404
