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

if [ ! -d "fixtures/${VARIANT}" ]; then
    echo "Building the local repositories..."
    python -m scripts.gen_fixture 2>/dev/null || python scripts/gen_fixture.py
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
