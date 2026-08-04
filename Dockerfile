# SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

# Build from the repository root, because the image carries both halves:
#
#     docker build -t rstuf-visualizer .
#
# The interface is served by the same process as the API, so an operator
# deploys one container rather than a backend and a web server.

# --- dependencies -----------------------------------------------------------
#
# Resolved in a throwaway stage so neither pipenv nor a build cache reaches
# the image that ships. Versions come from Pipfile.lock and are installed with
# their hashes, so a build either produces the audited dependency set or fails.

FROM python:3.13-slim AS dependencies

RUN pip install --no-cache-dir pipenv==2026.7.1

WORKDIR /build
COPY backend/Pipfile backend/Pipfile.lock ./

RUN pipenv requirements --hash > requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --require-hashes \
       -r requirements.txt

# --- runtime ----------------------------------------------------------------

FROM python:3.13-slim

LABEL org.opencontainers.image.title="RSTUF Visualizer" \
      org.opencontainers.image.description="Read-only web view of a TUF \
repository managed by Repository Service for TUF" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/repository-service-tuf"

COPY --from=dependencies /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The layout of the source tree is kept, so the backend finds the interface
# beside it, exactly as it does when run from a checkout.
WORKDIR /srv/backend
COPY backend/app ./app
COPY frontend /srv/frontend

# Nothing here writes to its own files. The one directory the service does
# write is the trust directory under /tmp, which holds the metadata the TUF
# client has verified, so a read-only root filesystem needs /tmp mounted and
# nothing else.
RUN useradd --create-home --uid 1001 visualizer \
    && chown -R visualizer:visualizer /srv
USER visualizer

EXPOSE 8000

# For anyone running this outside Kubernetes. A cluster uses the probes in the
# chart instead, and both ask the same endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request as r; \
r.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
