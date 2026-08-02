# Design

How the visualizer reads a TUF repository, checks it, shows it, and ships.

Everything here was verified: against `tuf 7.0.0` and `fastapi 0.141.1` as
installed, against RSTUF's own source, and against a running RSTUF deployment.

---

## 1. What the service does

A browser asks for a view of a repository. The backend fetches the repository's
signed metadata, has `python-tuf` check it, shapes the result into small JSON,
and returns it. It stores nothing and changes nothing.

```
Browser  ──HTTP──►  our backend  ──HTTP──►  signed metadata (storage)
         ◄──JSON──               ──HTTP──►  RSTUF API (status only)
                       never                database, broker, worker
```

The database is unsigned, private, and can change under us. The signed files
are the only thing we can check, so they are the only thing we read.

### Why a backend at all

A TUF client for the browser exists (`tuf-js`), so the checking could in
principle run client-side. A backend earns its place four ways: one cache
serves every viewer instead of each browser re-fetching the repository; the
browser talks to a single origin, so no cross-site setup is needed for the
RSTUF API; size caps and timeouts are enforced somewhere the viewer cannot
disable them; and the response shapes stay stable while the metadata format
moves. It is also the one place a future write path can attach.

---

## 2. Three sets of addresses

Keeping these apart is the core of the design. The browser only ever talks to
Set A.

| Set | Direction | Addresses |
|---|---|---|
| A | browser → our backend | `/api/v1/overview`, `/api/v1/roles/{role}`, `/api/v1/artifacts`, `/api/v1/status`, `/api/v1/roots` |
| B | our backend → RSTUF API | `/api/v1/config/`, `/api/v1/bootstrap/`, `/api/v1/metadata/sign` |
| C | our backend → storage | `timestamp.json`, `{version}.{role}.json` |

Set A is versioned the way RSTUF's own API is: everything under `/api/v1/`,
so a changed response shape can ship as `/api/v2/` beside the old one instead
of breaking it. Only `/healthz` sits at the root, because probes are
configured once and should never move. The version prefix also keeps API
routes cleanly apart from the frontend, which owns every other path.

Set C carries the trust picture and is checked. Set B carries live status and is
not, because status is not a security claim.

The division that matters: **no metadata file is ever fetched by a call we
write.** Set C is a plain base URL handed to the client, which fetches and
checks every file behind it. Set B never carries metadata. It answers
questions the metadata cannot: whether the repository has been bootstrapped,
what is waiting to be signed, and which readable name belongs to a key.

The single exception proves the rule. The trust anchor arrives through Set B,
because trust cannot be bootstrapped by the files being checked. The client
requires those bytes to be handed to it and never fetches them itself.

---

## 3. Getting the trust anchor

To check any signature we need one root we already trust. Three sources, tried
in order:

| Order | Source | Use | Strength |
|---|---|---|---|
| 1 | `RSTUF_TRUSTED_ROOT` | production | strongest: arrives out of band |
| 2 | `GET /api/v1/config/` → `trusted_root` | normal | good, needs no setup |
| 3 | nothing | never | refuse to start |

Source 2 was confirmed against a live deployment: the config endpoint returns
the complete signed root, so no operator has to paste anything.

Trust-on-first-use is not offered. The library removed it, and now requires an
explicit `bootstrap` argument with no default, so the choice cannot be made by
accident.

One honest limit on source 2: the root arrives from the RSTUF API, a different
service from the storage being checked. That is safer than taking the root from
the storage itself, and weaker than a root an operator hands over.

---

## 4. Reading the repository

### The library does the checking

```python
updater = Updater(
    metadata_dir=str(trust_dir),
    metadata_base_url=settings.metadata_url,
    target_base_url=settings.artifacts_url,
    fetcher=VisualizerFetcher(settings),
    config=updater_config,
    bootstrap=root_bytes,
)
await asyncio.to_thread(updater.refresh)
```

`refresh()` resolves and checks root, timestamp, snapshot and targets:
signatures, thresholds, expiry, and rollback. We never check metadata
ourselves.

It runs on a worker thread because the library's network calls are
synchronous. Awaiting it directly would stall every other request for the
length of a fetch.

Refreshes are also single-flight: when several requests miss the cache at
once, one of them refreshes while the rest wait for its result behind a lock.
However many browsers arrive together, the storage sees one fetch per cache
window, and two refreshes never write the trust directory at the same time.

Nothing here runs on a timer. The client checks expiry when it is called, and
it is called when a browser asks and the cache has gone stale, so the work
follows demand. A page left open therefore asks again on an interval of its
own, which stays cheap because the cache absorbs it.

`refresh()` does **not** load delegated roles. Those load on demand, which
suits a screen that only shows them when asked.

### Our own network layer

The library accepts a replacement fetcher, and that is where our own
behaviour belongs:

```python
class VisualizerFetcher(FetcherInterface):
    def _fetch(self, url: str) -> Iterator[bytes]:
        ...
```

It carries our timeout, retries, request logging, and any headers a
deployment behind a gateway needs. Swapping the transport later touches no
other file.

### Client settings

```python
UpdaterConfig(
    max_root_rotations=256,
    max_delegations=32,
    root_max_length=512_000,
    timestamp_max_length=16_384,
    snapshot_max_length=2_000_000,
    targets_max_length=5_000_000,
    prefix_targets_with_hash=True,
    app_user_agent="rstuf-visualizer/0.1.0",
)
```

The length caps bound how much we read before giving up, so a storage server
cannot feed us an unbounded file. `prefix_targets_with_hash` must be
configurable because RSTUF's own client reads it from a per-repository
setting, and getting it wrong breaks artifact paths. `app_user_agent` lets an
operator recognise us in their logs.

### Building the tree costs no extra fetches

After `refresh()`, the trust directory holds the checked files. The tree comes
from three of them:

```
root.json      → thresholds, key counts, key names
snapshot.json  → the version of every role, delegated ones included
targets.json   → the delegation rule
```

From the rule, the library derives every delegated role name. A repository
with `bit_length = 4` yields sixteen roles, `bins-0` through `bins-f`. Nothing
is downloaded to learn this, and no role name appears in our code.

### Opening one delegated role

A role's contents load only when someone opens it. The parent checks the
child, using public interfaces:

```python
targets.signed.verify_delegate(name, child.signed_bytes, child.signatures)
result = targets.signed.get_verification_result(
    name, child.signed_bytes, child.signatures
)
```

A role edited after signing is rejected with a message naming the shortfall,
for example `bins-0 was signed by 0/1 keys`. A role that verifies yields its
artifact list: path, length, and hashes.

---

## 5. Reporting what was found

| Situation | Response | Reason |
|---|---|---|
| everything checks out | `200` | normal |
| expired or badly signed | `200` with a status | showing broken trust is the point |
| repository not set up | `200`, marked not ready | a real state, not a failure |
| RSTUF API unreachable | `200`, status panel hidden | status is not essential |
| unknown role in the path | `404` | it does not exist, and the check blocks path tricks |
| malformed query value | `422` | rejected before our code runs |
| storage unreachable | `502` / `503` | nothing can be shown |
| no trust anchor | `503` | nothing can be checked |

The library's own error types map onto this cleanly:

```
RepositoryError            broken trust   → 200 with a status
├── ExpiredMetadataError       expired
├── UnsignedMetadataError      invalid
├── BadVersionNumberError      invalid  (rollback)
└── LengthOrHashMismatchError  invalid

DownloadError              broken system  → 502 / 503
```

Confirmed against generated repositories. Real messages: `timestamp.json is
expired`, and `targets was signed by 0/1 keys`.

### Reading the API's replies carefully

When nothing awaits signing, `/api/v1/metadata/sign` returns a message and no
`data` field at all, so the absence of that field must be handled rather than
assumed to be an empty list.

A repository can also report itself ready while its storage holds no files,
because the two live in different places. The interface shows that as a
repository which is ready but has no readable metadata, not as a crash.

### What an expired role actually means

RSTUF's worker renews metadata on its own. A scheduled task runs every five
minutes, and any online role within an hour of expiring gets its version and
expiry date bumped and is signed again.

So in a healthy deployment expiry should never be visible. When this service
does show an expired role, the metadata is not merely stale: the worker that
renews it has stopped or is failing. The interface says so, which makes an
expired badge a warning about the deployment rather than a note about a file.

Renewal belongs to the worker. This service only reports, and never writes.

---

## 6. What the browser receives

Responses carry only the fields a screen needs, so the interface depends on a
stable shape rather than on the metadata format.

```
RoleSummary   name, version, expires, threshold, key_count, status
KeySummary    id, name, scheme, location, held_offline
TreeEdge      parent, child
OverviewResponse
              state, roles[], edges[], message
```

---

## 7. Screens

| Screen | Endpoint | Shows |
|---|---|---|
| roles table | `/api/v1/overview` | every role with signers, threshold, expiry, status |
| tree | `/api/v1/overview` | the same data drawn as a graph |
| role detail | `/api/v1/roles/{role}` | keys, signatures, expiry, and a link to the raw file |
| artifacts | `/api/v1/artifacts` | path, hash and size, searchable and paged |
| status | `/api/v1/status` | whether the repository is ready, and what awaits signing |
| root history | `/api/v1/roots` | what changed between two versions of root |

The table is the landing view because it is dense and scannable. The tree
answers "who delegates to whom" at a glance.

A deployment normally points at one repository, set by its operator. Where a
demo deployment wants visitors to explore, the landing page can offer example
repositories to load, the way public TUF viewers do.

When the repository is not ready, one short card replaces the table:

| State | Card |
|---|---|
| not set up | "Repository not set up yet" |
| starting | "Setting up repository" |
| awaiting signatures | "Waiting for signatures" |
| ready | the table and tree |

### Naming keys instead of showing hashes

RSTUF records a readable name on every key, and where an online key lives:

```
x-rstuf-key-name        root_key_1, root_key_2, online_key
x-rstuf-online-key-uri  awskms:alias/aws-test-key
```

Showing those instead of a 64-character identifier turns an unreadable list
into something an operator recognises. Where the field is absent, the
identifier is shown, shortened.

### Making the online and offline split visible

A typical repository protects root with several offline keys and signs
everything else with one shared online key:

```
root                     root_key_1 + root_key_2   offline, threshold 2
targets, timestamp,      online_key                online, threshold 1
snapshot, and the bins
```

That arrangement is the security model, and raw metadata hides it. Marking
each key as offline or online, and showing which roles share one, states it
plainly.

### Comparing versions of root

Root is the anchor, and rotating keys means publishing a new version of it.
Comparing two versions reports what changed: version and expiry, keys added,
removed or altered, thresholds, which keys began signing, and which stopped.
This is how a signer confirms a rotation went as intended.

Old versions are fetched by their spec-defined names, `1.root.json` onward,
and checked before anything is shown: the specification's rotation rule says
version N must be signed to threshold by the keys of version N−1 *and* by its
own, and the library's `verify_delegate` applies exactly that check to each
step of the chain. An unverifiable version is shown as unverifiable, never as
history.

### Drawing a tree that stays readable

The tree is laid out by a hierarchical layout engine rather than by hand, so
the shape follows the data. Delegated roles are collapsed behind a single node
by default and expand on request, because a repository may hold sixteen of
them or two hundred and fifty-six, and drawing them all at once helps nobody.

---

## 8. Designed to keep working

Each row is a real mechanism, not an intention.

| What can differ between repositories | How the code copes |
|---|---|
| number of delegated roles | derived from the rule, any count |
| named roles instead of a rule | both forms already handled |
| depth of delegation | followed by the library, bounded by a setting |
| the network itself | replaceable through the fetcher interface |
| where the trust anchor lives | three ordered sources |
| artifact path style | a setting, matching RSTUF's client |
| where metadata lives | a setting, never a code path |
| how responses are cached | callers see a two-method interface, so a shared store such as Redis can replace the in-process cache without touching them |
| more than one repository | the metadata layer takes the repository as an argument rather than reading global state, so a second repository is added by configuration |
| the browser contract | versioned under `/api/v1/`, so a new shape ships beside the old one |

One rule inside the code: the tree builder iterates over what it finds and
never names a role.

Write operations stay out of scope. When they arrive they attach at the
backend, which is the single place a browser request already passes through.

---

## 9. Packaging

The frontend is built to static files, which the backend serves. FastAPI
offers this directly:

```python
app.frontend("/", directory="dist")
```

API routes are matched first; the frontend is reached only when nothing else
matched. One image, one origin, and no cross-site problem to solve.

The image is built in stages, matching the pattern used by RSTUF's own
services: dependencies resolved in a builder stage, then only the installed
packages and the application copied into a slim final image.

```
frontend build ─┐
                ├─►  one image  ─►  ghcr.io  ─►  Helm chart  ─►  rstuf-demo
backend       ──┘
```

---

## 10. Deployment

The chart follows the shape of RSTUF's existing charts, so an operator meets
nothing unfamiliar:

```
templates/
├── deployment.yaml       image, probes, environment, security context
├── service.yaml
├── ingress.yaml
├── serviceaccount.yaml
├── hpa.yaml
├── _helpers.tpl
├── NOTES.txt
└── tests/test-connection.yaml
```

Settings arrive as environment variables declared in values, the same way
RSTUF passes its own. Adding the chart to the demo is one dependency entry,
switched by `enabled`, as every other component there already is.

`/healthz` answers for the orchestrator only. It reports that the process is
running and says nothing about the repository, whose health appears on screen.

The pod holds no state worth keeping. The trust directory and the response
cache are both rebuilt from the trust anchor within seconds, so they live in
ephemeral storage, replicas need nothing shared, and scaling is a replica
count. TLS, authentication and rate limits belong to the ingress, which is
where RSTUF's other services already put them; the service itself stays
read-only and unauthenticated, like the repository it displays.

---

## 11. Layout

```
backend/
├── app/
│   ├── main.py          builds the application, serves the frontend
│   ├── config.py        settings, read once at startup
│   ├── cache.py         short-lived reuse of built responses
│   ├── api/routes.py    the endpoints
│   ├── tuf/
│   │   ├── fetcher.py   our network layer
│   │   ├── trust.py     owns the library's client
│   │   └── read.py      checked files → responses
│   ├── rstuf/client.py  the read-only API calls
│   └── models/schemas.py the response shapes
├── scripts/             generates local test repositories
└── tests/
frontend/                built at image time, served by the backend
```

---

## 12. Working on it

Three repositories with signed metadata are generated locally: one valid, one
expired, one edited after signing. They are built with real keys, so the
metadata layer is exercised against genuine signatures rather than
placeholders.

Tests that need the TUF client skip themselves where the platform cannot
support it, and state why, so a green run never hides a gap. The whole suite
passes on Linux, which is where the service actually runs; on Windows the six
client tests skip and the rest pass.

Verified end to end against a local URL, with the client pointed at
`http://127.0.0.1:PORT/` and no API in the path:

```
good       root, snapshot, targets, timestamp all valid;
           targets delegates to bins-0, bins-1
expired    verification stopped: timestamp.json is expired
tampered   verification stopped: targets was signed by 0/1 keys
```

---

## 13. Known limits

**Which role expired.** When checking stops, the library names the first
problem it met. Naming every affected role means reading each file's date
separately, which we do for files already saved.

**Windows.** The library caches the trust anchor behind a symbolic link, which
Windows refuses without Developer Mode. Containers are unaffected.

**Status without files.** A repository can report itself ready while its
storage is empty. The interface reports that plainly rather than treating it
as a failure.

**No metrics yet.** The service logs but does not export counters. Every
request passes one middleware stack, so metrics attach there later without
touching a route.
