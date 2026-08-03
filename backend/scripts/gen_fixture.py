# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

"""Generate a small, correctly signed TUF repository for local testing.

Creates three variants under ``fixtures/``:

    good/       every role valid and in date
    expired/    same keys, but timestamp already past its expiry
    tampered/   a signed file edited after signing, so its signature fails

The key arrangement mirrors a real RSTUF repository: root is held offline,
and one shared online key signs everything else. Keys carry the readable
names RSTUF records, so the interface can show names instead of hashes.

Run it with the project's virtualenv active::

    python scripts/gen_fixture.py

Serve one of the variants over HTTP and point RSTUF_METADATA_URL at it.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from securesystemslib.signer import CryptoSigner
from tuf.api.metadata import (
    DelegatedRole,
    Delegations,
    Metadata,
    MetaFile,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import JSONSerializer

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

ONLINE_ROLES = ("timestamp", "snapshot", "targets")
BINS = ["bins-0", "bins-1"]

KEY_NAME = "x-rstuf-key-name"
ONLINE_KEY_URI = "x-rstuf-online-key-uri"


def _expiry(days: int) -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
        days=days
    )


def _named(signer: CryptoSigner, name: str, online: bool) -> CryptoSigner:
    """Record RSTUF's readable key name, and mark online keys as such."""
    fields = signer.public_key.unrecognized_fields
    fields[KEY_NAME] = name
    if online:
        fields[ONLINE_KEY_URI] = f"fn:{signer.public_key.keyid}"
    return signer


def _build(out_dir: Path, timestamp_expiry_days: int) -> None:
    """Write a complete, signed repository into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Root is protected by a key kept offline; one online key signs the rest,
    # including the bins. This is the arrangement RSTUF sets up by default.
    root_signer = _named(CryptoSigner.generate_ecdsa(), "root_key_1", False)
    online_signer = _named(CryptoSigner.generate_ecdsa(), "online_key", True)

    # --- root: names every role's keys and how many signatures each needs ---
    root = Root(expires=_expiry(365))
    root.add_key(root_signer.public_key, "root")
    for name in ONLINE_ROLES:
        root.add_key(online_signer.public_key, name)
    root.roles["root"].threshold = 1

    # --- targets: delegates all artifacts to the bins ---
    targets = Targets(expires=_expiry(90))
    targets.delegations = Delegations(
        keys={online_signer.public_key.keyid: online_signer.public_key},
        roles={
            name: DelegatedRole(
                name=name,
                keyids=[online_signer.public_key.keyid],
                threshold=1,
                terminating=False,
                paths=[f"{name}/*"],
            )
            for name in BINS
        },
    )

    # --- bins: hold the artifact listings ---
    bins: dict[str, Targets] = {}
    for index, name in enumerate(BINS):
        bin_targets = Targets(expires=_expiry(30))
        bin_targets.targets[f"{name}/example-{index}.tar.gz"] = TargetFile(
            length=1024 * (index + 1),
            hashes={"sha256": f"{index}" * 64},
            path=f"{name}/example-{index}.tar.gz",
        )
        bins[name] = bin_targets

    # --- snapshot: pins the version of every other metadata file ---
    snapshot = Snapshot(expires=_expiry(5))
    snapshot.meta["targets.json"] = MetaFile(version=1)
    for name in BINS:
        snapshot.meta[f"{name}.json"] = MetaFile(version=1)

    # --- timestamp: points at the current snapshot ---
    timestamp = Timestamp(expires=_expiry(timestamp_expiry_days))
    timestamp.snapshot_meta = MetaFile(version=1)

    to_write: list[tuple[str, object, CryptoSigner]] = [
        ("root", root, root_signer),
        ("targets", targets, online_signer),
        ("snapshot", snapshot, online_signer),
        ("timestamp", timestamp, online_signer),
    ]
    to_write += [(name, bins[name], online_signer) for name in BINS]

    for name, payload, signer in to_write:
        metadata = Metadata(payload)
        metadata.sign(signer)
        # Consistent snapshot: every file is version-prefixed except timestamp.
        filename = (
            "timestamp.json" if name == "timestamp" else f"1.{name}.json"
        )
        metadata.to_file(str(out_dir / filename), JSONSerializer())

    # A client bootstraps from this copy, so keep an unprefixed one too.
    shutil.copy(out_dir / "1.root.json", out_dir / "root.json")


def _tamper(source: Path, destination: Path) -> None:
    """Copy a repository, then edit a signed file without re-signing."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    targets_path = destination / "1.targets.json"
    document = json.loads(targets_path.read_text(encoding="utf-8"))
    # Bump the version inside the signed payload. The signature still covers
    # the old value, so verification must fail.
    document["signed"]["version"] = 99
    targets_path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def main() -> None:
    if FIXTURES.exists():
        shutil.rmtree(FIXTURES)

    _build(FIXTURES / "good", timestamp_expiry_days=1)
    _build(FIXTURES / "expired", timestamp_expiry_days=-1)
    _tamper(FIXTURES / "good", FIXTURES / "tampered")

    for variant in ("good", "expired", "tampered"):
        files = sorted(p.name for p in (FIXTURES / variant).iterdir())
        print(f"{variant:10} {len(files)} files: {', '.join(files)}")


if __name__ == "__main__":
    main()
