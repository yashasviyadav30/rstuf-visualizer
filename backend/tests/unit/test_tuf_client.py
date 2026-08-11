# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Turning the configured trust anchor into root metadata bytes."""

from __future__ import annotations

import base64

import pytest

from app.client.tuf_client import (
    MetadataUnavailableError,
    resolve_trusted_root,
)
from tests.base import UnitTestCase


class TestResolveTrustedRoot(UnitTestCase):
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
