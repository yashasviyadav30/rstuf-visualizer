# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for metadata fetching and verification."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.models.schemas import RoleStatus
from app.tuf.trust import (
    MetadataUnavailableError,
    load_repository,
    resolve_trusted_root,
)
from tests.conftest import requires_fixtures, requires_symlinks


class TestResolveTrustedRoot:
    def test_decodes_inline_metadata(self) -> None:
        payload = b'{"signed": {"_type": "root"}}'

        resolved = resolve_trusted_root(base64.b64encode(payload).decode())

        assert resolved == payload

    def test_rejects_input_that_is_not_base64(self) -> None:
        with pytest.raises(ValueError, match="base64"):
            resolve_trusted_root("this is not base64!")

    def test_reports_an_unreachable_url(self) -> None:
        pointer = base64.b64encode(b"http://127.0.0.1:1/root.json").decode()

        with pytest.raises(MetadataUnavailableError):
            resolve_trusted_root(pointer, timeout=0.5)


@requires_fixtures
@requires_symlinks
class TestLoadRepository:
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
        # for each role rather than from a single repository-wide setting.
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
