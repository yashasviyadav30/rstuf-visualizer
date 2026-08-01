# Design

How the visualizer reads a TUF repository, checks it, and shows it. Every fact
here was checked against `tuf 7.0.0`, the RSTUF source, and a running RSTUF
deployment.

---

## 1. What the service does

A browser asks our backend for a view of a repository. The backend fetches the
repository's signed metadata, has `python-tuf` check it, shapes the result into
small JSON, and returns it. It stores nothing and changes nothing.

```
Browser  ──HTTP──►  our backend  ──HTTP──►  signed metadata (storage)
         ◄──JSON──               ──HTTP──►  RSTUF API (status only)
                       never                database, broker, worker
```

The database is unsigned, private, and can change under us. The signed files
are the only thing we can check, so they are the only thing we read.

---

## 2. Three sets of addresses

Keeping these apart is the core of the design. The browser only ever talks to
Set A.

| Set | Direction | Addresses |
|---|---|---|
| A | browser → our backend | `/overview`, `/roles/{role}`, `/artifacts`, `/status`, `/healthz` |
| B | our backend → RSTUF API | `/api/v1/config/`, `/api/v1/bootstrap/`, `/api/v1/metadata/sign` |
| C | our backend → storage | `timestamp.json`, `{version}.{role}.json` |

Set C carries the trust picture and is checked. Set B carries live status and is
not, because status is not a security claim.

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

Trust-on-first-use is not offered. `python-tuf` removed it, and the client now
requires an explicit `bootstrap` argument with no default, so the choice cannot
be made by accident.

One honest limit on source 2: the root arrives from the RSTUF API, a different
service from the storage being checked. That is safer than taking the root from
the storage itself, and weaker than a root an operator hands over.

---

## 4. Reading the repository

### The client does the checking

```python
updater = Updater(
    metadata_dir=str(trust_dir),
    metadata_base_url=settings.metadata_url,
    target_base_url=settings.artifacts_url,
    config=updater_config,
    bootstrap=root_bytes,
)
await asyncio.to_thread(updater.refresh)
```

`refresh()` resolves and checks root, timestamp, snapshot and targets:
signatures, thresholds, expiry, and rollback. We never check metadata
ourselves.

It runs on a worker thread because the client's network calls are synchronous.
Awaiting it directly would stall every other request for the length of a fetch.

`refresh()` does **not** load delegated roles. Those load on demand, which suits
a screen that only shows them when asked.

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

The length caps bound how much we will read before giving up, which stops a
storage server from feeding us an unbounded file. `prefix_targets_with_hash`
must be configurable because RSTUF's own client reads it from a per-repository
setting; getting it wrong breaks artifact paths. `app_user_agent` lets an
operator recognise us in their logs.

### Building the tree costs no extra fetches

After `refresh()`, the trust directory holds the checked files. The tree comes
from three of them:

```
root.json      → thresholds and key counts
snapshot.json  → the version of every role, delegated ones included
targets.json   → the delegation rule
```

From the rule, `python-tuf` derives every delegated role name. A repository with
`bit_length = 4` yields sixteen roles, `bins-0` through `bins-f`. Nothing is
downloaded to learn this, and no name appears in our code.

A bin's own contents load only when someone opens it.

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

The client's own error types map onto this cleanly:

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

### Signature counts

`Targets.get_verification_result()` returns which keys signed and which are
missing, so a role can be reported as waiting on a named number of signatures
rather than simply invalid.

### Opening one delegated role

A role's own contents load only when someone opens it. The parent checks the
child, using the same library and no internal interfaces:

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

## 6. What the browser receives

Responses carry only the fields a screen needs, so the interface depends on a
stable shape rather than on the metadata format.

```
RoleSummary   name, version, expires, threshold, key_count, status
TreeEdge      parent, child
OverviewResponse
              state, roles[], edges[], message
```

---

## 7. Screens

| Screen | Endpoint | Shows |
|---|---|---|
| roles table | `/overview` | every role with signers, threshold, expiry, status |
| tree | `/overview` | the same data drawn as a graph |
| role detail | `/roles/{role}` | keys, signatures, expiry, and a link to the raw file |
| artifacts | `/artifacts` | path, hash and size, searchable and paged |
| status | `/status` | whether the repository is ready, and what awaits signing |
| root history | `/roots` | what changed between two versions of root |

The table is the landing view because it is dense and scannable; the tree
answers "who delegates to whom" at a glance.

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
removed or altered, thresholds, which keys now sign, and which stopped. This is
how a signer confirms a rotation went as intended.

When the repository is not ready, one short card replaces the table:

| State | Card |
|---|---|
| not set up | "Repository not set up yet" |
| starting | "Setting up repository" |
| awaiting signatures | "Waiting for signatures" |
| ready | the table and tree |

---

## 8. Designed to keep working

Each row below is a real mechanism, not an intention.

| What can differ between repositories | How the code copes |
|---|---|
| number of delegated roles | derived from the rule, any count |
| named roles instead of a rule | both forms already handled |
| depth of delegation | followed by the client, bounded by a setting |
| the network itself | replaceable through the client's fetcher interface |
| where the trust anchor lives | three ordered sources |
| artifact path style | a setting, matching RSTUF's client |
| where metadata lives | a setting, never a code path |

One rule inside the code: the tree builder iterates over whatever it finds and
never names a role.

Write operations stay out. When they arrive they attach at the backend, which
is the single place a browser request already passes through.

---

## 9. Deployment

The frontend is built into static files that the backend serves, so the whole
tool is one image and the page and its data share an origin.

```
build  →  one image  →  ghcr.io  →  Helm chart  →  rstuf-demo
```

The chart follows the shape used by RSTUF's existing charts: a deployment,
service, ingress, service account, autoscaler, and a connection test, with
settings supplied through values.

`/healthz` answers for the orchestrator only. It reports that the process is
running and says nothing about the repository, whose health appears on screen.

---

## 10. Layout

```
backend/
├── app/
│   ├── main.py          builds the application
│   ├── config.py        settings, read once at startup
│   ├── cache.py         short-lived reuse of built responses
│   ├── api/routes.py    the endpoints
│   ├── tuf/
│   │   ├── fetcher.py   our network layer
│   │   ├── trust.py     owns the client
│   │   └── read.py      checked files → responses
│   ├── rstuf/client.py  the read-only API calls
│   └── models/schemas.py the response shapes
├── scripts/             local test repositories
└── tests/
```

---

## 11. Known limits

**Which role expired.** When checking stops, the client names the first problem
it met. Naming every affected role means reading each file's date separately,
which we do for files already saved.

**Windows.** The client caches the trust anchor behind a symbolic link, which
Windows refuses without Developer Mode. Containers are unaffected.

**Status without files.** A repository can report itself ready while its storage
is empty, because the two live in different places. The interface shows this as
a repository that is ready but has no readable metadata, rather than as a
failure.
