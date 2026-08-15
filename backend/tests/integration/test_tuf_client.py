# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Fetching and verifying a repository, against real signatures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.client.tuf_client import (
    MetadataUnavailableError,
    load_delegated_role,
    load_repository,
)
from app.dto.schemas import RoleStatus
from tests.base import RepositoryTestCase
from tests.conftest import FIXTURE_ROOT


class TestLoadRepository(RepositoryTestCase):
    @pytest.mark.asyncio
    async def test_accepts_a_valid_repository(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        view = await load_repository(
            metadata_url=serve_fixture("good"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("good"),
        )

        assert view.is_trustworthy
        names = {role.name for role in view.roles}
        assert {"root", "timestamp", "snapshot", "targets"} <= names
        assert all(role.status is RoleStatus.VALID for role in view.roles)

    @pytest.mark.asyncio
    async def test_reads_thresholds_from_root(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        view = await load_repository(
            metadata_url=serve_fixture("good"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("good"),
        )

        by_name = {role.name: role for role in view.roles}
        # Root asks for two of its two offline keys; the online roles ask for
        # one. Reading both proves the threshold comes from root's own entry
        # for each role, not from a single repository-wide setting.
        assert by_name["root"].threshold == 2
        assert by_name["root"].key_count == 2
        assert by_name["timestamp"].threshold == 1
        assert by_name["timestamp"].key_count == 1

    @pytest.mark.asyncio
    async def test_walks_the_root_chain_from_an_old_anchor(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        """A pinned root does not go stale.

        The anchor handed over is version one. The client is expected to
        follow the rotations published since and settle on the newest, which
        is what makes pinning a root safe to do once and leave alone.
        """
        view = await load_repository(
            metadata_url=serve_fixture("good"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("good"),
        )

        root = next(role for role in view.roles if role.name == "root")
        assert root.version == 3
        assert view.is_trustworthy

    @pytest.mark.asyncio
    async def test_discovers_delegations_without_naming_them(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        view = await load_repository(
            metadata_url=serve_fixture("good"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("good"),
        )

        targets = next(role for role in view.roles if role.name == "targets")
        assert targets.delegates_to == ["bins-0", "bins-1"]

    @pytest.mark.asyncio
    async def test_reports_expired_metadata_instead_of_raising(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        view = await load_repository(
            metadata_url=serve_fixture("expired"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("expired"),
        )

        assert not view.is_trustworthy
        assert "expired" in view.verification_error.lower()

    @pytest.mark.asyncio
    async def test_reports_a_broken_signature_instead_of_raising(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        view = await load_repository(
            metadata_url=serve_fixture("tampered"),
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("tampered"),
        )

        assert not view.is_trustworthy
        assert "signed by" in view.verification_error.lower()

    @pytest.mark.asyncio
    async def test_raises_when_the_repository_is_unreachable(
        self, tmp_path: Path, bootstrap_root
    ) -> None:
        with pytest.raises(MetadataUnavailableError):
            await load_repository(
                metadata_url="http://127.0.0.1:1/",
                trust_dir=tmp_path,
                bootstrap=bootstrap_root("good"),
            )


class TestARolledBackBin(RepositoryTestCase):
    """A correct signature says a file is genuine, not that it is current.

    An old bin signed by the same online key verifies perfectly while listing
    artifacts the repository has withdrawn. Snapshot names the version each
    delegated role should be at, and that entry is what makes the swap
    visible.
    """

    @pytest.mark.asyncio
    async def test_a_bin_older_than_snapshot_pins_is_not_valid(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        url = serve_fixture("rolled-back")
        view = await load_repository(
            metadata_url=url,
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("rolled-back"),
        )

        delegated = await load_delegated_role(url, view, "bins-0")

        assert delegated.status is RoleStatus.INVALID
        assert "snapshot pins version 2" in delegated.note

    @pytest.mark.asyncio
    async def test_the_other_bin_is_unaffected(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        url = serve_fixture("rolled-back")
        view = await load_repository(
            metadata_url=url,
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("rolled-back"),
        )

        delegated = await load_delegated_role(url, view, "bins-1")

        assert delegated.status is RoleStatus.VALID


class TestOneBinServedAsAnother(RepositoryTestCase):
    """Under succinct_roles every bin shares one key set and one threshold.

    The signature check cannot tell bins-0 from bins-1, because the keys the
    delegation names are the same for both. What binds the bytes to the name
    asked for is the entry snapshot records, and the type inside the file.
    """

    @pytest.mark.asyncio
    async def test_a_file_that_is_not_targets_is_refused(
        self, tmp_path: Path, serve_directory, bootstrap_root
    ) -> None:
        published = tmp_path / "published"
        shutil.copytree(FIXTURE_ROOT / "good", published)
        # Answer the request for a bin with root metadata instead. It is
        # genuine and correctly signed; it is simply not a bin.
        shutil.copy(published / "1.root.json", published / "1.bins-0.json")

        url = serve_directory(published)
        view = await load_repository(
            metadata_url=url,
            trust_dir=tmp_path / "trust",
            bootstrap=bootstrap_root("good"),
        )

        with pytest.raises(MetadataUnavailableError, match="not targets"):
            await load_delegated_role(url, view, "bins-0")


class TestABinSnapshotDoesNotList(RepositoryTestCase):
    """Snapshot is what says a role belongs to this repository at all.

    Without an entry there is nothing to check the file against, so accepting
    it would mean taking the file's own word for which role it is.
    """

    @pytest.mark.asyncio
    async def test_a_role_missing_from_snapshot_is_not_valid(
        self, tmp_path: Path, serve_fixture, bootstrap_root
    ) -> None:
        url = serve_fixture("good")
        view = await load_repository(
            metadata_url=url,
            trust_dir=tmp_path,
            bootstrap=bootstrap_root("good"),
        )
        snapshot = view.documents["snapshot"]
        del snapshot.signed.meta["bins-0.json"]

        delegated = await load_delegated_role(url, view, "bins-0")

        assert delegated.status is RoleStatus.INVALID
        assert "snapshot records nothing" in delegated.note
