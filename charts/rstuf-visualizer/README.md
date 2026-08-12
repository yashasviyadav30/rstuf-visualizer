# rstuf-visualizer

A read-only web view of a TUF repository managed by
[RSTUF](https://repository-service-tuf.readthedocs.io/).

The service fetches the repository's signed metadata, verifies it with
`python-tuf`, and shows the trust state: which roles are valid, what has
expired, who signs what, and how root reached its current version. It writes
nothing back. Changing a repository is the RSTUF API's job, reached with the
operator's own credentials.

## Installing

```bash
helm install visualizer charts/rstuf-visualizer \
  --set metadataUrl=http://rstuf-metadata/ \
  --set-file trustedRoot.value=root.json.b64
```

## What it needs

**An address serving the metadata.** `metadataUrl` is required and has no
default, because where the files are published differs with every
deployment and a guess would install cleanly while pointing at nothing.

RSTUF's docker-compose deployment publishes its storage with a small web
server on port 8080. In the `rstuf-demo` chart, the object store answers
directly: the worker writes every metadata object with a `public-read` ACL by
default, under the filenames a TUF client asks for, so point this at the
bucket.

```bash
--set metadataUrl=http://rstuf-localstack.rstuf.svc.cluster.local:4566/tuf-metadata/
```

On real S3 the same holds, unless the account has Block Public Access turned
on. That overrides the ACL, and then a web server or a signed-URL proxy has
to stand in front of the bucket.

**A trust anchor, ideally.** Every other file is checked against one root.
Supply the root you already trust through `trustedRoot`. Left unset, the
anchor is taken from the RSTUF API instead, which is weaker: it then arrives
from the same deployment being checked. With neither, the service reports
that it can verify nothing at all. It will not show metadata it has not
checked.

## Values

| Key | Default | Purpose |
|---|---|---|
| `metadataUrl` | *(required)* | base URL serving the signed metadata |
| `apiUrl` | `http://rstuf-api` | RSTUF API; empty hides the status panel |
| `trustedRoot.value` | `""` | base64 root metadata, or a base64 URL pointing at it |
| `trustedRoot.existingSecret` | `""` | use a Secret you manage instead |
| `trustedRoot.key` | `trusted-root` | key within that Secret |
| `cacheTtlSeconds` | `30` | how long a verified view stays reusable |
| `requestTimeoutSeconds` | `10` | ceiling on any single upstream request |
| `image.repository` | `ghcr.io/repository-service-tuf/rstuf-visualizer` | |
| `image.tag` | chart `appVersion` | |
| `service.type` | `ClusterIP` | |
| `service.port` | `80` | |
| `containerPort` | `8000` | the process runs unprivileged, so it cannot bind a low port |
| `ingress.enabled` | `false` | |
| `autoscaling.enabled` | `false` | |
| `trustDir.sizeLimit` | `64Mi` | space for the metadata the client has verified |

`values.yaml` carries the rest, with the same names and shapes as the other
RSTUF charts.

## How it is run

The pod needs no write access to its own files and is given none: the root
filesystem is read-only, privilege escalation is off, every capability is
dropped, and it runs as an unprivileged user with no Kubernetes credentials
mounted. The one directory it writes is an `emptyDir` holding the metadata
the TUF client has verified. Losing that costs one verification pass, so
nothing is persisted.

Both probes ask `/healthz`, which reports only that the process is running.
A repository in trouble is what this service exists to show, so it must never
be what takes the pod down.
