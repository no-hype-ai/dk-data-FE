# SeaweedFS S3 Client (`dk_data.ingestion.storage.minio_admin`)

**Scope**: operator-facing runbook for the SeaweedFS S3 object-store
client shipped in Horizon 2 / C.1. Covers environment configuration,
bucket layout, credential rotation, and the path-style addressing
gotcha that bites every new consumer exactly once.

The module is named `minio_admin.py` on purpose — it matches the
dk-alchemy naming convention where "MinIO" refers to the S3 API
surface, not the implementation. Under the hood we talk to SeaweedFS.

---

## Environment variables

All three **required** vars are materialized from a Doppler secret in
production (set on the hydrate Job / dk-data service):

| Env var                    | Required | Example                                   | Notes |
|----------------------------|----------|-------------------------------------------|-------|
| `SEAWEEDFS_S3_ENDPOINT`    | yes      | `http://seaweedfs-s3:8333`                | No trailing slash required; stripped if present. Never hardcode a cluster DNS name into code — always read from env. |
| `SEAWEEDFS_S3_ACCESS_KEY`  | yes      | (20-char alphanumeric)                    | S3 access key id. Doppler-managed in prod. |
| `SEAWEEDFS_S3_SECRET_KEY`  | yes      | (40+ chars URL-safe base64)               | S3 secret access key. Never log this value. |
| `SEAWEEDFS_S3_REGION`      | no       | `us-east-1` (default)                     | SigV4 requires a region string; value is only validated by shape. |
| `SEAWEEDFS_S3_BUCKET`      | no       | `dk-data-prestaged` (default)             | Default bucket used when a key is passed without an explicit bucket. |

`ObjectStore.from_env()` raises `RuntimeError` with a clear list of the
missing variables if any required var is absent or empty.

---

## Bucket layout

| Bucket              | Purpose                                                   |
|---------------------|-----------------------------------------------------------|
| `dk-data-prestaged` | `pg_dump -Fc` artifacts consumed by feature-005 hydration. Keys mirror `${source}/${schema}.${table}.dump`. |
| `dk-data-backups`   | (Future) CNPG barman base backups + WAL archive — owned by dk-alchemy issue #648. |

Object keys within `dk-data-prestaged` follow the prestaged-hydration
layout documented in `.dk/specs/005-prestaged-hydration/`. This
PR lands the client only; the hydration-flow integration is a
follow-up PR gated on feature/005 merging (we do not modify
`src/dk_data/ingestion/prestaged.py` here).

---

## Rotating credentials via Doppler

Credentials live in the Doppler project that feeds the hydrate Job
(`dk-data` project, `prd` config, secret group
`infra/seaweedfs-s3`). Rotate them like this:

1. Generate a fresh access/secret pair in the SeaweedFS admin console
   (or via the SeaweedFS `master.toml` static credentials file if the
   deployment uses that — check the CNPG/SeaweedFS runbook for the
   current mode).
2. In Doppler, **create** the new values alongside the old ones:
   ```
   doppler secrets set \
     SEAWEEDFS_S3_ACCESS_KEY=<new-access> \
     SEAWEEDFS_S3_SECRET_KEY=<new-secret> \
     --project dk-data --config prd
   ```
3. Restart the consuming workload so the new env is picked up:
   ```
   kubectl -n dk-data rollout restart deployment/dk-data
   kubectl -n dk-data delete job prestaged-hydrate --ignore-not-found
   ```
4. Watch a hydration run (or a `from_env().ensure_bucket(...)` probe)
   succeed against the new credentials.
5. Only then, **revoke the old credentials** in SeaweedFS. If you
   revoke before step 4 the workload will 403 on the next object
   operation.

Do not check credentials into the repo, into test fixtures, into
runbook examples, or into Doppler templates. The test suite in
`tests/unit/test_minio_admin.py` uses `moto` in-process — no real
endpoint is ever contacted.

---

## Path-style addressing gotcha

SeaweedFS's S3 gateway routes by **path prefix** (`/<bucket>/<key>`),
not by DNS subdomain (`<bucket>.<host>/<key>`). boto3 defaults to
virtual-hosted / DNS-style addressing, which 404s against SeaweedFS
because the Host header ends up as `<bucket>.seaweedfs-s3` instead of
`seaweedfs-s3`.

`ObjectStore._s3()` pins `addressing_style="path"` on the client
config, so anything going through `ObjectStore` is safe. If you need
to construct a boto3 client directly (e.g. for a one-off repair
script), **always** pass:

```python
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url=os.environ["SEAWEEDFS_S3_ENDPOINT"],
    aws_access_key_id=os.environ["SEAWEEDFS_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["SEAWEEDFS_S3_SECRET_KEY"],
    region_name="us-east-1",
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 2, "mode": "standard"},
    ),
)
```

Symptoms of the missing `addressing_style="path"`:

* `botocore.exceptions.EndpointConnectionError: Could not connect to
  the endpoint URL: "http://<bucket>.seaweedfs-s3:8333/..."` — DNS for
  `<bucket>.seaweedfs-s3` is not resolvable in-cluster.
* 404 on what should be a successful `head_object` — the gateway sees
  the Host header and routes the request to the wrong handler.

---

## Public API summary

Defined in `src/dk_data/ingestion/storage/minio_admin.py`:

| Method                                                        | Purpose                                          |
|---------------------------------------------------------------|--------------------------------------------------|
| `ObjectStore.ensure_bucket(name)`                             | Idempotent create — swallows `BucketAlreadyOwnedByYou` / `BucketAlreadyExists`. |
| `ObjectStore.put_artifact(local_path, key, content_type=...)` | Upload a local file under `<default_bucket>/<key>`. |
| `ObjectStore.get_artifact(key, local_path)`                   | Download `<default_bucket>/<key>` to disk.       |
| `ObjectStore.list_prefix(prefix)`                             | Iterate object summaries under a prefix (paginated). |
| `ObjectStore.presigned_url(key, expires_in=3600)`             | Generate a presigned GET URL.                    |
| `from_env()`                                                  | Factory — reads env vars, raises `RuntimeError` if any required var missing. |

See also: plan §C.1, dk-alchemy issue #648 (CNPG barman →
SeaweedFS) — the downstream infra work that will consume this module.
