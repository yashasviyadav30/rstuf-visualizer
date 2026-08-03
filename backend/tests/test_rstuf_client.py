# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Tests for reading the RSTUF API."""

from __future__ import annotations

import base64
import json

from app.rstuf.client import _root_bytes

ROOT = {"signatures": [{"keyid": "abc", "sig": "def"}], "signed": {}}


class TestTrustAnchorForms:
    """The anchor arrives in more than one shape.

    A running deployment answers ``/api/v1/config/`` with the root metadata
    itself, as JSON. The RSTUF client's configuration file holds the same
    document base64 encoded. Both are read, because both are the anchor.
    """

    def test_reads_the_document_the_api_sends(self) -> None:
        resolved = _root_bytes(ROOT)

        assert json.loads(resolved) == ROOT

    def test_reads_a_base64_encoded_document(self) -> None:
        encoded = base64.b64encode(json.dumps(ROOT).encode()).decode()

        assert json.loads(_root_bytes(encoded)) == ROOT

    def test_reads_json_supplied_as_text(self) -> None:
        assert json.loads(_root_bytes(json.dumps(ROOT))) == ROOT

    def test_passes_bytes_through_untouched(self) -> None:
        payload = json.dumps(ROOT).encode()

        assert _root_bytes(payload) == payload

    def test_does_not_mistake_json_for_base64(self) -> None:
        """A compact JSON document can be valid base64 by accident, so the
        shape is checked before the encoding is assumed."""
        resolved = _root_bytes('{"signed":{},"signatures":[]}')

        assert resolved.startswith(b"{")
