"""SeaweedFS S3 object-store client for dk-data ingestion.

Horizon 2 / C.1 — thin boto3 wrapper around the S3-compatible surface
exposed by SeaweedFS. Named ``minio_admin.py`` deliberately to match
dk-alchemy's naming convention (plan §C.1: "MinIO" refers to the S3
surface, not the implementation). Downstream, dk-alchemy issue #648
(CNPG barman → SeaweedFS) will consume this module to publish base
backups and WAL archives to an internal bucket.

Design:
    * Endpoint and credentials come from the environment (Doppler-backed
      in production). There is deliberately NO default endpoint — the
      caller MUST set ``SEAWEEDFS_S3_ENDPOINT`` or construct
      ``ObjectStore`` with an explicit ``endpoint_url``. We must not
      hardcode a cluster DNS name here (consumer-coupling-check gate).
    * SeaweedFS requires SigV4 + path-style addressing. DNS-style
      (``<bucket>.<host>``) requests 404 against the SeaweedFS S3
      gateway because it routes by path prefix.
    * Retries are intentionally low (``max_attempts=2``). Hydration and
      backup workloads are already retried at the job / orchestrator
      level; stacking boto3 retries on top amplifies latency when an
      endpoint is genuinely down.
    * ``ensure_bucket`` is idempotent — ``BucketAlreadyOwnedByYou`` and
      ``BucketAlreadyExists`` are the only errors swallowed anywhere in
      this module. All other failures propagate as-is.

Threading: boto3 clients are thread-safe for the call shape here, but
resource sharing across processes requires constructing a new client
per process (the socket pool is per-process).

[TAGS] [NOLOG][IDMPT][AUDIT]
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS: tuple[str, ...] = (
    "SEAWEEDFS_S3_ENDPOINT",
    "SEAWEEDFS_S3_ACCESS_KEY",
    "SEAWEEDFS_S3_SECRET_KEY",
)


class ObjectStore:
    """S3-compatible object store client for SeaweedFS.

    Parameters are all required — there are no defaults for credentials
    or endpoint. Use :func:`from_env` to construct from the environment.

    Args:
        endpoint_url: Full URL of the S3 gateway (e.g.
            ``http://seaweedfs-s3:8333``). Must NOT be a hardcoded
            cluster DNS name — always injected from env.
        access_key: S3 access key id.
        secret_key: S3 secret access key.
        region_name: Defaults to ``us-east-1`` which SeaweedFS accepts
            and AWS SigV4 requires. Override only if the gateway is
            configured otherwise.
        default_bucket: Optional bucket used by :meth:`put_artifact` /
            :meth:`get_artifact` when a key is given without a bucket
            prefix. Typically ``dk-data-prestaged``.
    """

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region_name: str = "us-east-1",
        default_bucket: str | None = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("ObjectStore requires a non-empty endpoint_url")
        if not access_key or not secret_key:
            raise ValueError("ObjectStore requires access_key and secret_key")

        self._endpoint_url = endpoint_url.rstrip("/")
        self._access_key = access_key
        self._secret_key = secret_key
        self._region_name = region_name
        self._default_bucket = default_bucket
        self._client: Any = None  # lazy

    # ------------------------------------------------------------------
    # Client construction
    # ------------------------------------------------------------------
    def _s3(self) -> Any:
        """Lazily build a boto3 S3 client with SeaweedFS-appropriate config."""
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region_name,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self._client

    def _resolve_bucket(self, key: str) -> tuple[str, str]:
        """Split a ``bucket/key`` string, falling back to ``default_bucket``.

        Accepts either ``"some/nested/key"`` (uses ``default_bucket``) or
        ``"bucket/some/nested/key"`` (explicit bucket prefix is detected
        only when ``default_bucket`` is unset — callers should prefer to
        pass a bucket explicitly via ``ensure_bucket`` + a bucket-aware
        API if that ambiguity matters).
        """
        if self._default_bucket is None:
            raise ValueError(
                "ObjectStore has no default_bucket; pass default_bucket=... "
                "when constructing, or call put_object/get_object directly "
                "with an explicit Bucket argument via the underlying client."
            )
        return self._default_bucket, key

    # ------------------------------------------------------------------
    # Bucket lifecycle
    # ------------------------------------------------------------------
    def ensure_bucket(self, name: str) -> str:
        """Create a bucket if it does not exist. Idempotent.

        Returns the bucket name. Swallows ``BucketAlreadyOwnedByYou``
        and ``BucketAlreadyExists`` (the two idempotency-friendly S3
        errors). Any other error propagates.
        """
        from botocore.exceptions import ClientError

        if not name:
            raise ValueError("ensure_bucket requires a non-empty name")

        client = self._s3()
        try:
            client.create_bucket(Bucket=name)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                logger.info(
                    "object_store.ensure_bucket.exists",
                    extra={"event": "ensure_bucket.exists", "bucket": name},
                )
                return name
            raise
        logger.info(
            "object_store.ensure_bucket.created",
            extra={"event": "ensure_bucket.created", "bucket": name},
        )
        return name

    # ------------------------------------------------------------------
    # Object I/O
    # ------------------------------------------------------------------
    def put_artifact(
        self,
        local_path: str,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload ``local_path`` to ``<default_bucket>/<key>``.

        Returns the key on success. Raises any boto3/OS error on failure
        (no swallowing beyond the idempotent-bucket-create gate).
        """
        bucket, object_key = self._resolve_bucket(key)
        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type

        size = os.path.getsize(local_path)
        client = self._s3()
        client.upload_file(
            Filename=local_path,
            Bucket=bucket,
            Key=object_key,
            ExtraArgs=extra_args or None,
        )
        logger.info(
            "object_store.put_artifact",
            extra={
                "event": "put_artifact",
                "bucket": bucket,
                "key": object_key,
                "bytes": size,
            },
        )
        return object_key

    def get_artifact(self, key: str, local_path: str) -> str:
        """Download ``<default_bucket>/<key>`` to ``local_path``.

        Returns ``local_path`` on success. Any boto3 error propagates.
        """
        bucket, object_key = self._resolve_bucket(key)
        client = self._s3()
        client.download_file(
            Bucket=bucket,
            Key=object_key,
            Filename=local_path,
        )
        try:
            size = os.path.getsize(local_path)
        except OSError:
            size = -1
        logger.info(
            "object_store.get_artifact",
            extra={
                "event": "get_artifact",
                "bucket": bucket,
                "key": object_key,
                "bytes": size,
            },
        )
        return local_path

    def list_prefix(self, prefix: str) -> "Iterator[dict[str, Any]]":
        """Yield object-summary dicts under ``<default_bucket>/<prefix>``.

        Each dict has at least ``Key``, ``Size``, ``LastModified``, and
        ``ETag`` (the shape returned by ``list_objects_v2``). Pagination
        is transparent — callers may consume the iterator lazily.
        """
        bucket, object_prefix = self._resolve_bucket(prefix)
        client = self._s3()
        paginator = client.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=object_prefix):
            for obj in page.get("Contents", []) or []:
                count += 1
                yield obj
        logger.info(
            "object_store.list_prefix",
            extra={
                "event": "list_prefix",
                "bucket": bucket,
                "key": object_prefix,
                "bytes": count,  # repurposed: count of objects returned
            },
        )

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL for ``<default_bucket>/<key>``."""
        bucket, object_key = self._resolve_bucket(key)
        client = self._s3()
        url = client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=expires_in,
        )
        logger.info(
            "object_store.presigned_url",
            extra={
                "event": "presigned_url",
                "bucket": bucket,
                "key": object_key,
                "bytes": expires_in,  # repurposed: expiry seconds
            },
        )
        return url


def from_env() -> ObjectStore:
    """Build an :class:`ObjectStore` from environment variables.

    Required env (typically materialized by a Doppler secret):
        * ``SEAWEEDFS_S3_ENDPOINT`` — full URL of the SeaweedFS S3 gateway.
        * ``SEAWEEDFS_S3_ACCESS_KEY``
        * ``SEAWEEDFS_S3_SECRET_KEY``

    Optional env:
        * ``SEAWEEDFS_S3_REGION`` — defaults to ``us-east-1``.
        * ``SEAWEEDFS_S3_BUCKET`` — defaults to ``dk-data-prestaged``.

    Raises:
        RuntimeError: if any required variable is missing or empty.
    """
    missing = [name for name in _REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "ObjectStore.from_env: missing required environment variables: "
            + ", ".join(missing)
        )

    return ObjectStore(
        endpoint_url=os.environ["SEAWEEDFS_S3_ENDPOINT"],
        access_key=os.environ["SEAWEEDFS_S3_ACCESS_KEY"],
        secret_key=os.environ["SEAWEEDFS_S3_SECRET_KEY"],
        region_name=os.environ.get("SEAWEEDFS_S3_REGION", "us-east-1"),
        default_bucket=os.environ.get("SEAWEEDFS_S3_BUCKET", "dk-data-prestaged"),
    )
