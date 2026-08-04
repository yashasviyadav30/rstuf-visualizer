# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for the endpoints, driven against a served repository."""

from __future__ import annotations

from app import service as service_module
from app.tuf.trust import MetadataUnavailableError
from tests.conftest import requires_fixtures, requires_symlinks


@requires_fixtures
@requires_symlinks
class TestOverview:
    def test_describes_a_valid_repository(self, visualizer) -> None:
        body = visualizer("good").get("/api/v1/overview").json()

        assert body["status"] == "valid"
        names = {role["name"] for role in body["roles"]}
        assert {"root", "timestamp", "snapshot", "targets"} == names

    def test_names_delegated_roles_without_loading_them(
        self, visualizer
    ) -> None:
        """The whole point of the tree being cheap: bins are listed from the
        rule and from snapshot, so none of them is fetched to draw the page.
        """
        body = visualizer("good").get("/api/v1/overview").json()

        delegated = body["delegated"]
        assert [item["name"] for item in delegated] == ["bins-0", "bins-1"]
        assert all(item["loaded"] is False for item in delegated)
        assert all(item["version"] == 1 for item in delegated)

    def test_reports_keys_by_name(self, visualizer) -> None:
        body = visualizer("good").get("/api/v1/overview").json()

        root = next(r for r in body["roles"] if r["name"] == "root")
        timestamp = next(r for r in body["roles"] if r["name"] == "timestamp")
        assert sorted(root["key_names"]) == ["root_key_1", "root_key_2"]
        assert timestamp["key_names"] == ["online_key"]

    def test_grades_expiry_rather_than_only_flagging_it(
        self, visualizer
    ) -> None:
        body = visualizer("good").get("/api/v1/overview").json()

        bands = {role["name"]: role["band"] for role in body["roles"]}
        assert bands["timestamp"] == "critical"
        assert bands["snapshot"] == "expiring"
        assert bands["root"] == "valid"

    def test_draws_edges_from_root_and_from_targets(self, visualizer) -> None:
        body = visualizer("good").get("/api/v1/overview").json()

        edges = {(e["parent"], e["child"]) for e in body["edges"]}
        assert ("root", "timestamp") in edges
        assert ("targets", "bins-0") in edges

    def test_answers_normally_when_metadata_has_expired(
        self, visualizer
    ) -> None:
        """A repository in trouble is the subject of this service, so it is
        described rather than reported as a server failure."""
        response = visualizer("expired").get("/api/v1/overview")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "expired"
        assert "expired" in body["verification_error"]

    def test_answers_normally_when_a_signature_is_broken(
        self, visualizer
    ) -> None:
        response = visualizer("tampered").get("/api/v1/overview")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "invalid"
        assert "signed by" in body["verification_error"]


@requires_fixtures
@requires_symlinks
class TestRoleDetail:
    def test_opens_a_top_level_role(self, visualizer) -> None:
        body = visualizer("good").get("/api/v1/roles/root").json()

        assert body["name"] == "root"
        assert body["signed_by"][0]["name"] == "root_key_1"
        assert body["signed_by"][0]["online"] is False

    def test_opening_a_bin_fetches_and_checks_it(self, visualizer) -> None:
        body = visualizer("good").get("/api/v1/roles/bins-0").json()

        assert body["status"] == "valid"
        assert body["signatures_present"] == 1
        assert body["threshold"] == 1
        assert all(
            item["path"].startswith("bins-0/") for item in body["artifacts"]
        )

    def test_reports_the_key_the_parent_declared(self, visualizer) -> None:
        """A delegated role is signed by keys named in its parent, not by a
        top-level key, so the parent is where the signer is read from."""
        body = visualizer("good").get("/api/v1/roles/bins-0").json()

        assert body["signed_by"][0]["name"] == "online_key"
        assert body["signed_by"][0]["online"] is True

    def test_rejects_an_unknown_role(self, visualizer) -> None:
        response = visualizer("good").get("/api/v1/roles/not-a-role")

        assert response.status_code == 404

    def test_rejects_a_name_that_could_escape_the_path(
        self, visualizer
    ) -> None:
        response = visualizer("good").get("/api/v1/roles/..%2Froot")

        assert response.status_code in (404, 422)


@requires_fixtures
@requires_symlinks
class TestArtifacts:
    def test_lists_artifacts_from_the_delegated_roles(
        self, visualizer
    ) -> None:
        client = visualizer("good")
        body = client.get(
            "/api/v1/artifacts", params={"page_size": 500}
        ).json()

        # The total is what the bins between them declare, gathered by the
        # service rather than counted here.
        declared = sum(
            len(client.get(f"/api/v1/roles/{name}").json()["artifacts"])
            for name in ("bins-0", "bins-1")
        )
        assert body["total"] == declared
        assert {a["role"] for a in body["artifacts"]} == {"bins-0", "bins-1"}

    def test_filters_by_search_term(self, visualizer) -> None:
        body = (
            visualizer("good")
            .get("/api/v1/artifacts", params={"search": "urllib3-1.4"})
            .json()
        )

        assert body["total"] == 1
        assert body["artifacts"][0]["role"] == "bins-1"

    def test_pages_the_results(self, visualizer) -> None:
        client = visualizer("good")
        first = client.get(
            "/api/v1/artifacts", params={"page": 1, "page_size": 10}
        ).json()
        second = client.get(
            "/api/v1/artifacts", params={"page": 2, "page_size": 10}
        ).json()

        assert len(first["artifacts"]) == 10
        assert len(second["artifacts"]) == 10
        # Consecutive pages, not the same ten twice.
        assert {a["path"] for a in first["artifacts"]}.isdisjoint(
            a["path"] for a in second["artifacts"]
        )

    def test_a_default_page_holds_less_than_the_total(
        self, visualizer
    ) -> None:
        """The count and the rows describe different things, so a reader
        given fifty rows beside a total of sixty-four needs a way to the
        rest. This is the case the fixture exists to reach."""
        body = visualizer("good").get("/api/v1/artifacts").json()

        assert body["total"] > body["page_size"]
        assert len(body["artifacts"]) == body["page_size"]

    def test_rejects_a_page_number_below_one(self, visualizer) -> None:
        response = visualizer("good").get(
            "/api/v1/artifacts", params={"page": 0}
        )

        assert response.status_code == 422

    def test_names_the_roles_it_could_not_read(
        self, visualizer, monkeypatch
    ) -> None:
        """A bin that cannot be fetched costs its own artifacts and no
        others. A list quietly short of a hundred entries is worse than one
        that says which hundred are missing."""
        original = service_module.load_delegated_role

        async def one_bin_fails(metadata_url, view, name, timeout=10.0):
            if name == "bins-1":
                raise MetadataUnavailableError(f"could not fetch {name}")
            return await original(metadata_url, view, name, timeout)

        monkeypatch.setattr(
            service_module, "load_delegated_role", one_bin_fails
        )

        body = visualizer("good").get("/api/v1/artifacts").json()

        assert body["unavailable"] == ["bins-1"]
        assert {a["role"] for a in body["artifacts"]} == {"bins-0"}
        assert body["total"] > 0

    def test_reads_each_delegated_role_once_however_many_pages(
        self, visualizer, monkeypatch
    ) -> None:
        """Every artifact lives in a delegated role, so listing them means
        fetching each one. A repository can hold two hundred and fifty-six,
        and turning a page must not ask the storage server for all of them
        again.
        """
        fetched: list[str] = []
        original = service_module.load_delegated_role

        async def counted(metadata_url, view, name, timeout=10.0):
            fetched.append(name)
            return await original(metadata_url, view, name, timeout)

        monkeypatch.setattr(service_module, "load_delegated_role", counted)

        client = visualizer("good")
        client.get("/api/v1/artifacts", params={"page": 1})
        after_first = list(fetched)

        client.get("/api/v1/artifacts", params={"page": 2})
        client.get("/api/v1/artifacts", params={"search": "urllib3"})

        assert sorted(after_first) == ["bins-0", "bins-1"]
        assert fetched == after_first


@requires_fixtures
@requires_symlinks
class TestStatus:
    def test_says_so_when_no_rstuf_api_is_configured(self, visualizer) -> None:
        """Status is helpful, not load-bearing, so its absence is stated and
        the rest of the page still works."""
        response = visualizer("good").get("/api/v1/status")

        assert response.status_code == 200
        assert response.json()["available"] is False
