# RSTUF Visualizer

A read-only web view of a TUF repository managed by
[RSTUF](https://repository-service-tuf.readthedocs.io/).

The service fetches the repository's signed metadata, verifies it with
`python-tuf`, and renders the delegation tree so the trust state of a
repository can be read at a glance: which roles are valid, what has expired,
and what is still waiting for signatures.

Built during the LFX Mentorship with RSTUF. Work in progress.

## Requirements

- Python 3.12 or newer
- A running RSTUF deployment, or the local fixtures described below

## Running it

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Linux and macOS: source .venv/bin/activate
pip install -r requirements.txt

export RSTUF_METADATA_URL=http://localhost:8080
uvicorn app.main:app --reload
```

The API is then served on <http://localhost:8000>, with interactive
documentation at `/docs`.

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `RSTUF_METADATA_URL` | yes | base URL of the signed TUF metadata |
| `RSTUF_TRUSTED_ROOT` | no | base64 trust anchor, following the RSTUF client convention |
| `RSTUF_API_URL` | no | RSTUF API base URL; unset hides the status panel |
| `RSTUF_CACHE_TTL_SECONDS` | no | response reuse window, default 30 |
| `RSTUF_REQUEST_TIMEOUT_SECONDS` | no | upstream request ceiling, default 10 |

## Local test repositories

`scripts/gen_fixture.py` builds three small TUF repositories with real ECDSA
keys and real signatures:

| Fixture | Contents |
|---|---|
| `good` | every role valid and in date |
| `expired` | timestamp past its expiry |
| `tampered` | a signed file edited after signing |

```bash
cd backend
python scripts/gen_fixture.py
python -m http.server 8080 --directory fixtures/good
```

Point `RSTUF_METADATA_URL` at that server to exercise the metadata layer
against genuine signatures.

> On Windows, `python-tuf` caches the trust anchor using a symbolic link.
> Enable Developer Mode (Settings → Privacy & security → For developers) so
> the process may create one without administrator rights.

## Tests

```bash
cd backend
pytest
```

## Layout

```
backend/
├── app/
│   ├── main.py          application entry point
│   ├── config.py        settings read from the environment
│   ├── api/             HTTP endpoints
│   ├── tuf/             metadata fetching and verification
│   └── models/          response schemas
├── scripts/             development utilities
└── tests/
```
