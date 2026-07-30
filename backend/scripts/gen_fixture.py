"""Generate a small, correctly signed TUF repository for local testing.

Creates three variants under ``fixtures/``:

    good/       every role valid and in date
    expired/    same keys, but timestamp already past its expiry
    tampered/   a signed file edited after signing, so its signature fails

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
    Role,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)
from tuf.api.serialization.json import JSONSerializer

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

TOP_LEVEL = ["root", "timestamp", "snapshot", "targets"]
BINS = ["bins-0", "bins-1"]


def _expiry(days: int) -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=days)


def _build(out_dir: Path, timestamp_expiry_days: int) -> None:
    """Write a complete, signed repository into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # One signing key per role. Real repositories keep the root key offline.
    signers = {name: CryptoSigner.generate_ecdsa() for name in TOP_LEVEL}
    bin_signer = CryptoSigner.generate_ecdsa()

    # --- root: names every role's keys and how many signatures each needs ---
    root = Root(expires=_expiry(365))
    for name, signer in signers.items():
        root.add_key(signer.public_key, name)
    root.roles["root"].threshold = 1

    # --- targets: delegates all artifacts to the bins ---
    targets = Targets(expires=_expiry(90))
    targets.delegations = Delegations(
        keys={bin_signer.public_key.keyid: bin_signer.public_key},
        roles={
            name: DelegatedRole(
                name=name,
                keyids=[bin_signer.public_key.keyid],
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
    snapshot = Snapshot(expires=_expiry(7))
    snapshot.meta["targets.json"] = MetaFile(version=1)
    for name in BINS:
        snapshot.meta[f"{name}.json"] = MetaFile(version=1)

    # --- timestamp: points at the current snapshot ---
    timestamp = Timestamp(expires=_expiry(timestamp_expiry_days))
    timestamp.snapshot_meta = MetaFile(version=1)

    to_write: list[tuple[str, object, CryptoSigner]] = [
        ("root", root, signers["root"]),
        ("targets", targets, signers["targets"]),
        ("snapshot", snapshot, signers["snapshot"]),
        ("timestamp", timestamp, signers["timestamp"]),
    ]
    to_write += [(name, bins[name], bin_signer) for name in BINS]

    for name, payload, signer in to_write:
        metadata = Metadata(payload)
        metadata.sign(signer)
        # Consistent snapshot: every file is version-prefixed except timestamp.
        filename = "timestamp.json" if name == "timestamp" else f"1.{name}.json"
        metadata.to_file(str(out_dir / filename), JSONSerializer())

    # A client bootstraps from this copy, so keep an unprefixed one too.
    shutil.copy(out_dir / "1.root.json", out_dir / "root.json")


def _tamper(source: Path, destination: Path) -> None:
    """Copy a good repository, then edit a signed file without re-signing it."""
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
