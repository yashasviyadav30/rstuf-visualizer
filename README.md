# RSTUF Visualizer

A read-only web view of a TUF repository managed by
[RSTUF](https://repository-service-tuf.readthedocs.io/).

The service fetches the repository's signed metadata, verifies it with
`python-tuf`, and renders the delegation tree so the trust state of a
repository can be read at a glance: which roles are valid, what has expired,
and what is still waiting for signatures.

Read-only by design: it verifies and displays a repository, and changes
nothing in it. Altering a repository is the RSTUF API's job, reached with the
operator's own credentials.

## Requirements

- Python 3.13 or newer
- A running RSTUF deployment, or the local fixtures described below

## Running it

A TUF client reads a repository over HTTP, so something has to publish the
metadata before there is anything to look at. `run_local.sh` stands up both
halves: a web server in front of a generated repository, and the visualizer
pointed at its URL.

```bash
cd backend
pipenv install --dev
pipenv run ./scripts/run_local.sh          # or: make run-local
```

The interface and the API are both served on <http://localhost:8000>, with
interactive documentation at `/docs`. Pass `expired` or `tampered` to run
against a repository in trouble.

To run the service on its own, against a repository published elsewhere:

```bash
export RSTUF_METADATA_URL=https://example.org/metadata/
uvicorn app.main:app --reload
```

## Endpoints

Every route is a GET. This service reads a repository and changes nothing in
it.

| Route | Answers |
|---|---|
| `/api/v1/overview` | every role, its state, and the delegation tree |
| `/api/v1/roles/{role}` | one role's keys, signatures and expiry |
| `/api/v1/roles/{role}/raw` | the bytes that role was verified from |
| `/api/v1/roots` | how root reached its current version, rotation by rotation |
| `/api/v1/artifacts` | the artifacts the repository vouches for, searchable |
| `/api/v1/status` | what the RSTUF API reports, when one is configured |
| `/healthz` | that the process is alive, and nothing about the repository |

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `RSTUF_METADATA_URL` | yes | base URL of the signed TUF metadata |
| `RSTUF_TRUSTED_ROOT` | no | base64 trust anchor, following the RSTUF client convention |
| `RSTUF_API_URL` | no | RSTUF API base URL; unset hides the status panel |
| `RSTUF_CACHE_TTL_SECONDS` | no | response reuse window, default 30 |
| `RSTUF_REQUEST_TIMEOUT_SECONDS` | no | upstream request ceiling, default 10 |

## Container image

Built from the repository root, because the image carries the interface and
the backend together:

```bash
docker build -t rstuf-visualizer .

docker run -p 8000:8000 --read-only --tmpfs /tmp \
  -e RSTUF_METADATA_URL=http://metadata:8080/ \
  -e RSTUF_TRUSTED_ROOT="$(base64 -w0 root.json)" \
  rstuf-visualizer
```

It runs as an unprivileged user and writes nothing outside `/tmp`, where the
TUF client keeps the metadata it has verified.

## Helm chart

`charts/rstuf-visualizer` follows the shape of RSTUF's own charts.

```bash
helm install visualizer charts/rstuf-visualizer \
  --set metadataUrl=http://rstuf-metadata/ \
  --set-file trustedRoot.value=root.json.b64
```

`metadataUrl` is required and has no default. RSTUF writes metadata to
storage, and object storage is not an address a TUF client can read, so it
must point at whatever serves those files over HTTP. Note that the
`rstuf-demo` chart writes to a LocalStack S3 bucket with no public-read
policy, so that deployment has nothing to point at yet.

Without `trustedRoot`, the anchor is taken from the RSTUF API instead. That
is weaker, because it then arrives from the same deployment being checked.
With neither, the service reports that it cannot verify anything rather than
showing metadata it has not checked.

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

## Continuous integration

Three workflows, each running what a developer runs by hand:

| Workflow | Does |
|---|---|
| `tests.yml` | installs from `Pipfile.lock`, runs flake8, black, isort, bandit, then pytest |
| `chart.yml` | lints the chart, builds the image, installs both into a kind cluster and checks the repository verifies |
| `image.yml` | builds the image, runs it against a generated repository, publishes to ghcr.io on a `v*` tag |

`pipenv install --deploy` is used throughout, so a dependency added without
relocking fails the build rather than quietly resolving to something else.

## Layout

```
backend/
├── app/
│   ├── main.py          application entry point
│   ├── config.py        settings read from the environment
│   ├── api/             HTTP endpoints
│   ├── tuf/             metadata fetching and verification
│   ├── rstuf/           read-only calls to the RSTUF API
│   └── models/          response schemas
├── scripts/             development utilities
└── tests/
frontend/                the interface, served by the backend
charts/rstuf-visualizer/ the Helm chart
Dockerfile               builds both halves into one image
```
