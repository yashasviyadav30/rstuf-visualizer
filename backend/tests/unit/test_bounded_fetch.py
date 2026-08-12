# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""How much this service will read from a server it does not control.

The two files fetched by calls written here, a delegated role and an
archived root, arrive from storage belonging to whoever runs the
repository. How many bytes that is, is their decision until it is bounded
here.
"""

from __future__ import annotations

import http.server
import socketserver
import threading
from collections.abc import Iterator

import pytest

from app.client.tuf_client import MetadataUnavailableError, fetch_within
from tests.base import UnitTestCase


class _Endless(http.server.BaseHTTPRequestHandler):
    """Answers every request with a stream that does not end."""

    def do_GET(self) -> None:  # noqa: N802 - the name http.server requires
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b"x" * 8192)
        except (BrokenPipeError, ConnectionAbortedError, OSError):
            # Expected: the reader gave up, which is the point of the test.
            pass

    def log_message(self, *_args: object) -> None:
        pass


class _Oversized(_Endless):
    """Declares a size no reader should accept, then sends it."""

    def do_GET(self) -> None:  # noqa: N802
        body = b"y" * 40_000
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Reusable(socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture
def serve() -> Iterator[object]:
    servers: list[socketserver.TCPServer] = []

    def _serve(handler: type[http.server.BaseHTTPRequestHandler]) -> str:
        server = _Reusable(("127.0.0.1", 0), handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}/anything.json"

    yield _serve

    for server in servers:
        server.shutdown()
        server.server_close()


class TestReadingFromStorageWeDoNotControl(UnitTestCase):
    def test_stops_reading_a_stream_that_does_not_end(self, serve) -> None:
        """Counting the body after it arrives is not a limit.

        By the time the length is known the bytes are already held, so a
        server that keeps sending decides how much memory this process uses.
        """
        with pytest.raises(MetadataUnavailableError, match="larger than"):
            fetch_within(
                serve(_Endless), limit=64_000, timeout=10.0, what="a bin"
            )

    def test_refuses_a_body_that_declares_itself_too_large(
        self, serve
    ) -> None:
        """A server honest about its size saves the transfer entirely."""
        with pytest.raises(MetadataUnavailableError, match="larger than"):
            fetch_within(
                serve(_Oversized), limit=1_000, timeout=10.0, what="root"
            )

    def test_reads_a_file_inside_the_limit(self, serve) -> None:
        content = fetch_within(
            serve(_Oversized), limit=64_000, timeout=10.0, what="root"
        )

        assert content == b"y" * 40_000

    def test_reports_a_server_that_cannot_be_reached(self) -> None:
        with pytest.raises(MetadataUnavailableError, match="could not be"):
            fetch_within(
                "http://127.0.0.1:1/root.json",
                limit=1_000,
                timeout=0.5,
                what="root",
            )
