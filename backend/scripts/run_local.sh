#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT
#
# Run the visualizer against a locally generated repository.
#
#   ./scripts/run_local.sh [good|expired|tampered]
#
# Two processes stand up, matching production shape: a web server in front
# of the metadata files, and the visualizer pointed at its URL. The client
# is never handed a directory, because in a real deployment it never is.

set -euo pipefail

VARIANT="${1:-good}"
METADATA_PORT="${METADATA_PORT:-8080}"
APP_PORT="${APP_PORT:-8000}"

cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-$PWD}"

# The generated repositories carry a one-day timestamp, matching how RSTUF
# renews that role. Left alone they lapse overnight, and serving a stale one
# would report an expiry that says nothing about the code. Freshness is
# checked, not existence, and all three variants are rebuilt together
# so the deliberately expired one stays expired.
repositories_are_fresh() {
    python - <<'PY'
import datetime
import json
import pathlib
import sys

path = pathlib.Path("fixtures") / "good" / "timestamp.json"
try:
    expires = json.loads(path.read_text(encoding="utf-8"))["signed"]["expires"]
except (OSError, ValueError, KeyError):
    sys.exit(1)

when = datetime.datetime.fromisoformat(expires)
if when.tzinfo is None:
    when = when.replace(tzinfo=datetime.timezone.utc)
sys.exit(0 if when > datetime.datetime.now(datetime.timezone.utc) else 1)
PY
}

if ! repositories_are_fresh; then
    echo "Building the local repositories..."
    python scripts/gen_fixture.py
fi

python -m http.server -d "fixtures/${VARIANT}" "${METADATA_PORT}" \
    >/dev/null 2>&1 &
METADATA_PID=$!
trap 'kill "${METADATA_PID}" 2>/dev/null || true' EXIT

export RSTUF_METADATA_URL="http://127.0.0.1:${METADATA_PORT}/"
RSTUF_TRUSTED_ROOT="$(base64 -w0 "fixtures/${VARIANT}/root.json")"
export RSTUF_TRUSTED_ROOT

echo "repository : ${VARIANT}"
echo "metadata   : ${RSTUF_METADATA_URL}"
echo "visualizer : http://127.0.0.1:${APP_PORT}"
echo

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}"
