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

The shape that follows is a backend for frontend. This service is not a
general API for anyone to build on; it exists to answer the questions one
interface asks, and its responses are cut to those questions rather than
mirroring the metadata. That is why the browser never sees a TUF structure,
why two upstreams of different kinds sit behind one door, and why a screen
costs one request instead of five.

---

## 2. Three sets of addresses

Keeping these apart is the core of the design. The browser only ever talks to
Set A.

| Set | Direction | Addresses |
|---|---|---|
| A | browser → our backend | `/api/v1/overview`, `/api/v1/roles/{role}`, `/api/v1/roles/{role}/raw`, `/api/v1/artifacts/bins`, `/api/v1/artifacts`, `/api/v1/status`, `/api/v1/roots` |
| B | our backend → RSTUF API | `/api/v1/config/`, `/api/v1/bootstrap/`, `/api/v1/metadata/sign` |
| C | our backend → storage | `timestamp.json`, `{version}.{role}.json` |

Set A is versioned the way RSTUF's own API is: everything under `/api/v1/`,
so a changed response shape can ship as `/api/v2/` beside the old one instead
of breaking it. Only `/healthz` sits at the root, because probes are
configured once and should never move. The version prefix also keeps API
routes cleanly apart from the frontend, which owns every other path.

Set C carries the trust picture and is checked. Set B carries live status and is
not, because status is not a security claim.

The division that matters: **nothing is shown that was not checked against
something already trusted.** Set C is a plain base URL handed to the client,
which fetches the top-level chain behind it and verifies every file. Set B
never carries metadata. It answers questions the metadata cannot: whether the
repository has been bootstrapped, what is waiting to be signed, and which
readable name belongs to a key.

Two kinds of file are fetched by calls this service writes rather than by the
client, and both are checked before anything they contain reaches a screen:

| File | Fetched by | Checked against |
|---|---|---|
| a delegated role, when someone opens it | `client/tuf_client.py` | its parent's delegation entry, through `verify_delegate` |
| an older version of root, when reading history | `repositories/root_repository.py` | the version that superseded it, by the same call |

Neither is fetched by the client because the client has no reason to: it
resolves the chain it needs to verify the repository and stops. Bins load
only when asked, and superseded roots are not on the path to anything. So
this service asks for them itself, and then hands each one to the library to
check against a role that is already trusted. A file that fails is reported
as failing, never shown as history or as contents.

The trust anchor is the one file with nothing above it. It arrives through
Set B, because trust cannot be bootstrapped by the files being checked, and
the client requires those bytes to be handed to it rather than fetching them
itself.

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

A pinned root does not go stale. The client walks forward from whatever
version it was handed, fetching `2.root.json`, `3.root.json` and so on, and
verifies each rotation against the version before it. Root expiry, key
rotation and rollback are therefore the library's problem, not the
operator's, and the reason the settings allow a long chain of rotations.

One honest limit on source 2: the root arrives from the RSTUF API, a different
service from the storage being checked. That is safer than taking the root from
the storage itself, and weaker than a root an operator hands over.

---

## 4. Reading the repository

### The library does the checking

```python
updater = Updater(
    metadata_dir=str(trust_dir),
    metadata_base_url=metadata_url,
    bootstrap=bootstrap,
    config=UPDATER_CONFIG,
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

### Client settings

```python
UPDATER_CONFIG = UpdaterConfig(
    max_root_rotations=256,
    max_delegations=32,
    root_max_length=512_000,
    timestamp_max_length=16_384,
    snapshot_max_length=2_000_000,
    targets_max_length=5_000_000,
    app_user_agent="rstuf-visualizer/0.1.0",
)
```

The length caps bound how much is read before giving up, so a storage server
we do not control cannot answer a request for `timestamp.json` with an
endless stream. They are generous for real metadata: a repository with two
hundred and fifty-six bins has a snapshot listing all of them and is nowhere
near two megabytes. `max_root_rotations` is what makes pinning a root safe to
do once and leave alone, and `app_user_agent` lets an operator recognise us
in the logs of a server that belongs to someone else.

### The transport, and where ours would go

The library's own fetcher is what runs today. Its timeouts and its retry
behaviour are the library's, not ours.

`FetcherInterface` is the seam if that has to change. A deployment behind a
gateway needing particular headers, or one wanting request logging and
retries on our terms rather than the library's, gets a subclass passed as
`fetcher=`, and nothing outside this one call changes. That is worth knowing
about and worth not building until something asks for it: the default
fetcher's behaviour has been adequate against every repository this has been
run against, and a replacement is code that would have to be maintained
against a library that already ships one.

Our own timeout does apply to the two files this service fetches itself, the
delegated roles and the older roots, because those go through `httpx` calls
we wrote and `RSTUF_REQUEST_TIMEOUT_SECONDS` bounds them.

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

A failing delegated role is reported on its own rather than sinking the rest.
Bins are siblings, not a chain: one expired bin says nothing about the other
fifteen. Each carries its own status, so the tree shows exactly which one is
in trouble instead of collapsing into a single failure.

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
| role detail | `/api/v1/roles/{role}` | keys, signatures, expiry, and a link to the signed file |
| signed file | `/api/v1/roles/{role}/raw` | the bytes that role was verified from |
| artifact bins | `/api/v1/artifacts/bins` | every role holding artifacts, with a count each |
| artifacts | `/api/v1/artifacts` | path, hash and size, one bin at a time or searched across all |
| status | `/api/v1/status` | whether the repository is ready, and what awaits signing |
| root history | `/api/v1/roots` | what changed between two versions of root |

The table is the landing view because it is dense and scannable. The tree
answers "who delegates to whom" at a glance.

### Expiry is more than valid or expired

A role an hour from expiring is not in the same condition as one expiring next
year, and calling both "valid" hides the difference that matters. Four bands
are reported instead:

```
expired        already past its date
critical       under a day left
expiring       under a week left
valid          beyond that
```

Timestamp is the reason this earns its place. It is renewed roughly daily, so
it sits in the critical band during normal operation, and a countdown beside
it turns an abstract date into something a person can act on.

### One badge that means something

The header badge does **not** carry the worst band found anywhere. It cannot:
timestamp is inside a day of expiring whenever the repository is working
normally, so a badge showing the worst band would be amber for ever, and a
warning that is always on is not a warning.

It answers a narrower question. Something expired, or a signature that did not
check out, is wrong and turns it red. Root running down turns it amber,
because root is the one role no worker can renew: it is signed offline, by
people, and nothing rescues it automatically. Everything else is green.

The per-role bands stay in the table, where a one-day expiry on timestamp
reads as the ordinary information it is.

### Refreshing without defeating the cache

A refresh control sits beside the badge. The cache exists to spare the storage
server, not to argue with someone who wants the state right now.

But a visible button is pressed by everyone who arrives, every time, so
honouring every press would mean a full verification pass per visitor while
the repository has not moved. A refresh within five seconds of the last
reading is therefore declined, quietly and quickly. That is a rate limit
rather than a refusal: once the answer in hand is old enough that a new one
could differ, pressing it reads the repository again. RSTUF's own worker
renews metadata every few minutes, so nothing is lost.

The label beside it says how old the answer is in words, "checked 4 seconds
ago", rather than as a clock time. What sends someone to that button is not
knowing whether the screen is current, and saying so removes the reason to
press it. The age comes from the reading itself rather than from the clock at
the moment of replying, or a cached answer would claim to have been checked
the instant it was served.

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

The walk starts at the root the client already verified and runs backwards,
which is the only direction that proves anything. Confirming that version
N−1's keys signed version N shows those keys are the genuine ones, and since
N−1 carries their signatures too, the whole of N−1 is tied to something
already trusted. Walking forwards from version 1 would prove nothing, because
nothing vouches for version 1 but itself.

That walk also looks where a refresh never does. A client moves forward from
the root it holds, so once it has settled on the newest version it stops
reading the older ones. An archived root that is corrupted or swapped after
the fact therefore goes unnoticed by every normal client. Reading the history
is what finds it.

One detail that would otherwise mislead: a superseded version is not graded
for expiry. Old roots lapse as a matter of course, and a client checks expiry
on the final root alone, so painting version 1 red would raise an alarm about
a file nothing depends on.

### Serving the file a role was verified from

Each role links to the bytes behind it. The link points at this service, not
at the storage the file came from, for two reasons: the reader may have no
route to that storage, and a fresh fetch from it would return whatever is
there now, which nobody has checked. A top-level role is served from the
trust directory, where the client wrote what it accepted; a delegated role is
fetched and checked on request and the bytes that passed are the ones sent.

Those bytes come from a repository this service does not control, so they go
out as a download with `nosniff`, never as something a browser will render.

### Drawing a tree that stays readable

Node positions are computed, not written down. Leaves take the next free
column and a parent sits halfway between its first and last child, so the
shape follows the metadata: a repository that delegates differently draws
differently, and no role name appears in the layout. The alternative, a
layout library, would mean a build step the interface deliberately avoids,
and the shape a TUF repository makes is too shallow to need one.

Delegated roles are collapsed behind a single node by default and expand on
request, because a repository may hold sixteen of them or two hundred and
fifty-six. Expanded, they are drawn as a block of chips under one connector
rather than as two hundred and fifty-six separate branches, which would hide
the structure they are meant to show.

---

## 8. Designed to keep working

Each row is a real mechanism, not an intention.

| What can differ between repositories | How the code copes |
|---|---|
| number of delegated roles | derived from the rule, any count |
| named roles instead of a rule | both forms already handled |
| depth of delegation | followed by the library, bounded by a setting |
| the network itself | the library's fetcher runs today; `FetcherInterface` is the seam a replacement passes through, and it touches one call |
| where the trust anchor lives | three ordered sources |
| where metadata lives | a setting, never a code path |
| how responses are cached | callers see a two-method interface, so a shared store such as Redis can replace the in-process cache without touching them |
| more than one repository | the metadata layer takes the repository as an argument rather than reading global state, so a second repository is added by configuration |
| the browser contract | versioned under `/api/v1/`, so a new shape ships beside the old one |
| who signs a delegated role | read from the parent's own delegation entry, not inherited from a top-level role, so per-role signing keys are reported correctly |
| authentication and permissions | every request already passes one backend door, so a login and a per-role permission check slot in front of the routes without changing the metadata layer |

One rule inside the code: the tree builder iterates over what it finds and
never names a role.

Write operations stay out of scope. When they arrive they attach at the
backend, which is the single place a browser request already passes through,
and they use the RSTUF API, which is already the write side of the split:
reading goes through the TUF client, changing goes through RSTUF.

That shape matters for the repositories RSTUF is built for. A package index
of any size ends up with separate teams owning separate paths, each holding
its own online key, and the operations that follow are adding a delegation,
rotating a key, and deciding who may do either. A read-only viewer whose
backend can grow authentication, permissions and write endpoints reaches
those; one built as a browser-side reader does not.

---

## 9. Packaging

The backend serves the frontend, from the same process and the same origin.
FastAPI offers this directly:

```python
application.frontend("/", directory=str(FRONTEND_DIR))
```

It is registered last, so API routes and the health probe are matched first
and the interface only answers for paths nothing else claimed. One image, one
origin, and no cross-site arrangement for a browser to negotiate.

The interface is React and TypeScript, compiled by Vite, so the image builds
it rather than copying source. That is a third stage, alongside the one that
resolves Python dependencies, and only its output reaches the image that
ships: no Node, no `node_modules`, no TypeScript.

`npm ci` installs exactly what `package-lock.json` pins and fails when the two
have drifted, which is the guarantee `pipenv install --deploy` gives on the
other side.

The types the interface holds the backend to are generated from the backend's
own OpenAPI document rather than written by hand, so a field renamed on the
server becomes a compile error in the component that reads it instead of
`undefined` on a screen. `make openapi` refreshes them.

The image is built in stages, matching the pattern used by RSTUF's own
services: dependencies resolved in a builder stage, then only the installed
packages and the application copied into a slim final image.

```
frontend ──npm run build──┐
                          ├─►  one image  ─►  ghcr.io  ─►  chart  ─►  demo
backend  ──pipenv────────┘
```

Cross-origin access is off by default and exists for one case: a frontend
development server answers on a port of its own, which a browser treats as
another site. `RSTUF_CORS_ORIGINS` names the origins allowed to call the API,
and no credentials are permitted across them. Every route is a GET and none
reads a cookie, and it is that pairing, a permitted origin together with
credentials, that would let another site act as a visitor.

---

## 10. Deployment

The chart follows the shape of RSTUF's existing charts, so an operator meets
nothing unfamiliar:

```
templates/
├── deployment.yaml       image, probes, environment, security context
├── service.yaml
├── ingress.yaml
├── secret.yaml           the trust anchor
├── serviceaccount.yaml
├── hpa.yaml
├── _helpers.tpl
├── NOTES.txt
└── tests/test-connection.yaml
```

Settings arrive as environment variables declared in values, the same way
RSTUF passes its own. Adding the chart to the demo is one dependency entry,
switched by `enabled`, as every other component there already is.

The trust anchor goes in a Secret rather than into the deployment's
environment. Root metadata is published, so this is not a secret in the usual
sense, but it decides what the service will believe, and that deserves to be
as hard to edit unnoticed as a credential.

The pod needs no write access to its own files and is given none: the root
filesystem is read-only, privilege escalation is off, every capability is
dropped, and it runs as an unprivileged user. The single directory it does
write is the trust directory holding verified metadata, mounted as an
`emptyDir`. Losing that costs one verification pass, so nothing is persisted.

Both probes ask `/healthz`, which reports only that the process is running. A
repository in trouble is what this service exists to show, so it must never
be what takes the pod down.

### Serving the metadata

The client needs a URL, and a storage bucket alone is not one. Something must
answer HTTP requests for the metadata files, wherever they live.

RSTUF's own deployments answer this two different ways.

The docker-compose deployment publishes its storage over HTTP, with a small
server on port 8080 in front of the worker's directory.

The Helm demo has no such server, and an S3 bucket is not a URL. It turns out
not to need one. RSTUF's worker writes every metadata object with a
`public-read` ACL, and that is the default rather than something an operator
opts into:

```python
self._s3_object_acl = s3_object_acl or "public-read"
...
self._s3_client.put_object(Body=data, Bucket=..., Key=filename, ACL=...)
```

Objects land at the root of the bucket under the names a TUF client asks for,
`timestamp.json` and `{version}.{role}.json`, because that is what the client
passes as the key. So the object store answers for them directly, and in the
demo that address is:

```
http://rstuf-localstack.rstuf.svc.cluster.local:4566/tuf-metadata/
```

Checked rather than assumed: an object written with `--acl public-read` into
a LocalStack bucket created by `awslocal s3 mb`, exactly as the demo creates
it, is returned for an anonymous `GET` over plain HTTP with no credentials
and no signature. A key that was never written returns 404, so the 200 is the
object and not a catch-all.

Two limits on that result. It was reproduced against LocalStack directly
rather than inside the demo chart, so the address above is derived from the
chart's service name and port rather than observed in a cluster. And on real
S3 the same ACL is not enough on its own: an account with Block Public Access
turned on overrides it, which is a deliberate choice an operator makes and
not something this chart can decide for them.

The setting must work whether the files sit in S3, in a volume, or behind an
existing server, on cloud or on premise, which is why `metadataUrl` is
required and has no default. A guess would let the chart install cleanly
while pointing at nothing.

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

Folders are named for what a module does, so the order they may call each
other in falls out of the names. Handlers map requests onto services;
services hold the rules; repositories and the client reach outside the
process; DTOs know nothing about any of it.

```
backend/
├── app/
│   ├── main.py             assembles the application, serves the frontend
│   ├── config.py           settings, read once at startup
│   ├── handlers/           one module per subject, plus the URL patterns
│   │   ├── health.py       /healthz
│   │   ├── overview.py     the whole repository in one answer
│   │   ├── roles.py        one role, and the bytes it was verified from
│   │   ├── artifacts.py    the bins, and what they hold
│   │   ├── roots.py        root's history
│   │   └── status.py       what the RSTUF API reports
│   ├── middleware/
│   │   ├── logging.py      one line per request, and where metrics attach
│   │   └── auth.py         where authentication attaches; nothing enforced
│   ├── services/
│   │   ├── metadata_service.py    what a request needs, and what happens first
│   │   ├── presenters.py   checked metadata → response shapes
│   │   └── cache_service.py       short-lived reuse, single-flight on a miss
│   ├── repositories/
│   │   └── root_repository.py     older roots, fetched and checked
│   ├── client/
│   │   ├── tuf_client.py   owns the library's client and the trust anchor
│   │   └── rstuf_api_client.py    the read-only API calls
│   └── dto/schemas.py      the response shapes
├── scripts/                generates local test repositories
└── tests/
    ├── base.py             UnitTestCase, RepositoryTestCase
    ├── unit/               reaches nothing outside the process
    └── integration/        real keys, real signatures, real HTTP
frontend/                   React and TypeScript, built by Vite
├── index.html              the entry point
├── openapi.json            the backend's schema, and the source of the types
└── src/
    ├── api/                one fetch wrapper, and generated types
    ├── components/         what more than one page uses
    ├── hooks/              one request, and the three things a screen needs
    └── pages/              one folder per tab, each with its own
                            components, endpoints, hooks and types
```

`presenters.py` sits under `services/` rather than `repositories/` on
purpose. It fetches nothing and reads no source; it turns metadata the client
already verified into the shapes above. Filing it as a repository would name
it after something it does not do.

`metadata_service.py` is one class rather than several. The cache and its
per-key lock are state on that object, and they are what stops two
verification passes writing the same trust directory at once. Splitting it
would mean several locks guarding one directory, which no test running
sequentially would catch.

---

## 12. Working on it

Three repositories with signed metadata are generated locally: one valid, one
expired, one edited after signing. They are built with real keys, so the
metadata layer is exercised against genuine signatures rather than
placeholders.

Those files are served over HTTP by a small static server, which is the same
arrangement production uses: the client is handed a URL, never a directory.
Development therefore exercises the real path rather than a shortcut, and the
compose file that starts the server doubles as the reference for how an
operator puts a server in front of their own storage.

The suite is split by what each test is allowed to touch. Unit tests reach
nothing outside the process, so they run anywhere in under a second and a
failure names one module. Integration tests drive those generated
repositories and let python-tuf verify them, which is the only way to know a
signature checks out.

```
tests/unit           38 tests, under a second
tests/integration    53 tests, real keys and real signatures
tests/e2e             9 tests, a real browser on the real page
frontend/src         11 tests, the tree layout and the header verdict
```

The browser tests are the only layer that knows whether anything reached a
screen. Everything below them can pass while the page stays blank: a response
carrying the right fields is not a table a person can read. They start the
real application on a port, serving the compiled interface exactly as the
container does, and drive Chromium against a generated repository.

They run as a second pytest session rather than alongside the rest, and that
is not tidiness. Playwright's synchronous API drives an event loop of its own,
and once it has run in a session pytest-asyncio stops awaiting the async tests
that follow: they are collected, never run, and reported as failures. Keeping
the two apart costs nothing, since the browser tests need the interface
compiled and a browser installed while the others need neither.

Every test that cannot run says why and skips, so a green run never hides a
gap. On Windows all 53 integration tests skip, because the library caches its
trust anchor behind a symbolic link and Windows refuses that without Developer
Mode. The browser tests skip on three conditions of their own: the generator,
the symbolic link, a compiled interface, and an installed browser.
`make test-docker` runs everything on Linux, which is both where the service
runs and what CI checks.

That gap is not academic. A defect in the reported age of a reading sat
undetected because the test covering it was one of the ones skipping locally,
and it surfaced the first time the full suite ran.

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

**The library's transport.** Timeouts and retries against storage are
python-tuf's defaults, not ours. `FetcherInterface` is where a replacement
would go, and a deployment behind a gateway that needs particular headers is
the thing that would ask for one. Our own timeout does bound the two files
this service fetches itself.

**No authentication.** Deliberate: the service is read-only and the metadata
it displays is published. `middleware/auth.py` names the seam and enforces
nothing, which is the honest state to leave it in until write operations
exist.
