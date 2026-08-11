# Putting the visualizer into rstuf-demo

Notes for the RSTUF maintainers. The short version: the demo can serve its
metadata to a TUF client today, without adding a web server, and the change
to `rstuf-demo` is one dependency entry.

## The question

A TUF client is handed a URL and fetches `timestamp.json`,
`{version}.snapshot.json` and the rest from behind it. RSTUF writes metadata
to storage, and a bucket is not obviously a URL, so the first question for
any reader of a repository is what address to point it at.

The docker-compose deployment answers this by running a small web server on
port 8080 in front of the worker's directory. The Helm demo has no equivalent,
so the assumption was that the demo needed one added before anything could
read it.

That assumption was wrong.

## What is already true

`repository_service_tuf_worker/services/storage/awss3.py`:

```python
self._s3_object_acl = s3_object_acl or "public-read"      # line 41
...
self._s3_client.put_object(
    Body=data, Bucket=self._bucket, Key=filename, ACL=self._s3_object_acl
)
```

Two things follow. Every metadata object is written world-readable unless an
operator sets `AWS_S3_OBJECT_ACL` to something else, and the key is the plain
filename, so objects land at the root of the bucket under exactly the names a
client asks for.

The object store therefore answers for them directly. In the demo:

```
http://rstuf-localstack.rstuf.svc.cluster.local:4566/tuf-metadata/
```

## Checked, not assumed

Reproducing the write and fetching it with no credentials:

```console
$ docker run -d --name ls -p 4566:4566 localstack/localstack:3.8
$ docker exec ls awslocal s3 mb s3://tuf-metadata
make_bucket: tuf-metadata

$ docker exec ls awslocal s3api put-object --bucket tuf-metadata \
    --key timestamp.json --body /tmp/timestamp.json --acl public-read

$ curl -s -o /dev/null -w "%{http_code}\n" \
    http://localhost:4566/tuf-metadata/timestamp.json
200

$ curl -s -o /dev/null -w "%{http_code}\n" \
    http://localhost:4566/tuf-metadata/2.root.json
404
```

The bucket is created exactly as the demo's startup script creates it, with
`awslocal s3 mb` and no bucket policy. The 404 on a key that was never
written is there to show the 200 is the object rather than a catch-all.

## What this does not prove

**It was not run inside the chart.** LocalStack was driven directly, so the
address above comes from the chart's service name and port rather than from a
cluster. Installing the demo and fetching `timestamp.json` from inside it
would settle that, and is the one test worth running before anyone relies on
this.

**LocalStack 3.8, not the pinned version.** The demo depends on the
`localstack` chart at 0.6.25. Current LocalStack images require a licence key
to start, so 3.8 was used. Behaviour here is plain S3 ACL handling and is
unlikely to differ, but it is not the same image.

**Real S3 has one more switch.** An account with Block Public Access enabled
overrides a `public-read` ACL, and then the objects are not anonymously
readable whatever the worker wrote. That is a deliberate choice an operator
makes. A deployment in that position needs a web server or a signed-URL proxy
in front of the bucket, which is why `metadataUrl` in the visualizer chart is
required and has no default rather than defaulting to a bucket address.

## The change to rstuf-demo

One dependency entry and one values block, switched by `enabled` like every
other component:

```yaml
# Chart.yaml
- name: rstuf-visualizer
  version: 0.1.0
  repository: "https://repository-service-tuf.github.io/helm-charts"
  condition: rstuf-visualizer.enabled
```

```yaml
# values.yaml
rstuf-visualizer:
  enabled: true
  metadataUrl: "http://rstuf-localstack.rstuf.svc.cluster.local:4566/tuf-metadata/"
  apiUrl: "http://rstuf-api.rstuf.svc.cluster.local"
  initContainers:
    - name: wait-for-localstack
      image: busybox:1.37
      command: ['sh', '-c', 'until nc -z rstuf-localstack.rstuf.svc.cluster.local 4566 ; do sleep 2; done;']
  ingress:
    enabled: true
    hosts:
      - host: visualizer.local
```

The trust anchor is left unset, so the visualizer asks the RSTUF API for it
through `GET /api/v1/config/`. That is the weaker of its two sources, because
the root then arrives from the same deployment being checked, and it is the
right trade for a demo where nobody has a root to hand over. Any install that
matters should set `trustedRoot` instead.

## What is needed from RSTUF

**The chart has to be published.** The dependency entry points at
`repository-service-tuf.github.io/helm-charts`, which does not carry
`rstuf-visualizer` yet. Until it does, the entry resolves to nothing. That is
a decision about whether this belongs in the org's chart repository, and it
is the only thing blocking the integration.

**A version bump.** The change above takes `rstuf-demo` from 0.3.14 to 0.4.0,
since it adds a component rather than fixing one.
