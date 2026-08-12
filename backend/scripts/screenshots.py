# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Photograph each screen, against a repository built for the purpose.

The pictures in the documents are taken by this script rather than by hand,
so they cannot drift from what the interface actually draws. Run it after a
change that alters a screen:

    make screenshots

It needs the interface compiled and a browser installed, the same two
conditions the browser tests carry.
"""

from __future__ import annotations

import base64
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
FIXTURES = BACKEND / "fixtures"
IMAGES = ROOT / "docs" / "images"

# Wide enough that the two columns sit side by side, which is the layout an
# operator sees; tall enough that the roles table and the tree fit together.
VIEWPORT = {"width": 1400, "height": 900}

SHOTS = (
    ("roles", "Roles", "overview"),
    ("roots", "Root history", "root-history"),
    ("artifacts", "Artifacts", "artifacts"),
    ("status", "Status", "status"),
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    sys.path.insert(0, str(BACKEND))

    import uvicorn
    from playwright.sync_api import sync_playwright

    from app.config import get_settings
    from app.main import create_app
    from app.services.metadata_service import get_metadata_service

    variant = sys.argv[1] if len(sys.argv) > 1 else "good"
    repository = FIXTURES / variant
    if not (repository / "root.json").exists():
        print(f"no fixture at {repository}; run `make fixtures` first")
        return 1

    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        print("the interface is not built; run `make build-frontend` first")
        return 1

    metadata_port = _free_port()
    metadata = subprocess.Popen(  # noqa: S603 - a fixed local command
        [
            sys.executable,
            "-m",
            "http.server",
            str(metadata_port),
            "--directory",
            str(repository),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    import os

    os.environ["RSTUF_METADATA_URL"] = f"http://127.0.0.1:{metadata_port}/"
    os.environ["RSTUF_TRUSTED_ROOT"] = base64.b64encode(
        (repository / "root.json").read_bytes()
    ).decode()
    os.environ.pop("RSTUF_API_URL", None)
    get_settings.cache_clear()
    get_metadata_service.cache_clear()

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(), host="127.0.0.1", port=port, log_level="warning"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)

    IMAGES.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=2)
            page.goto(f"http://127.0.0.1:{port}/")

            for _, label, name in SHOTS:
                if label == "Roles":
                    # With nothing selected the detail panel is an empty half
                    # of the picture. Opening a role shows what the screen is
                    # actually for.
                    page.get_by_role("button", name="root", exact=True).click()
                else:
                    # The screens are links now, each with its own address.
                    page.get_by_role("link", name=label).click()
                # The artifacts screen reads nothing until a bin is opened,
                # so open one: a picture of the empty state would say less
                # about the screen than the screen says about itself.
                if label == "Artifacts":
                    page.get_by_role(
                        "button", name="bins-0", exact=False
                    ).click()
                page.wait_for_timeout(400)
                page.screenshot(path=str(IMAGES / f"{name}.png"))
                print(f"wrote docs/images/{name}.png")

            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        metadata.terminate()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
