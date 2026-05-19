"""Unit tests for ``dk_data.ingestion.storage.minio_admin``.

Uses ``moto`` (the AWS mock library) to stand up an in-process S3 server
so the tests never reach out to the real SeaweedFS deployment. No
fixture secrets are checked in — ``from_env`` receives dummy values via
monkeypatch, and the ``mock_aws`` harness accepts any credentials.

Horizon 2 / C.1.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.filterwarnings(
    "ignore::DeprecationWarning",
)

# moto is a dev-only dep; skip the module cleanly if absent so lint/CI
# on a minimal image doesn't fail here.
moto = pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")
from botocore.exceptions import ClientError  # noqa: E402

from dk_data.ingestion.storage import ObjectStore, from_env  # noqa: E402
from dk_data.ingestion.storage import minio_admin  # noqa: E402


# ---------------------------------------------------------------------------
# from_env: required-env validation
# ---------------------------------------------------------------------------
def test_from_env_raises_when_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SEAWEEDFS_S3_ENDPOINT",
        "SEAWEEDFS_S3_ACCESS_KEY",
        "SEAWEEDFS_S3_SECRET_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        from_env()

    message = str(excinfo.value)
    assert "SEAWEEDFS_S3_ENDPOINT" in message
    assert "SEAWEEDFS_S3_ACCESS_KEY" in message
    assert "SEAWEEDFS_S3_SECRET_KEY" in message


def test_from_env_raises_when_one_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEAWEEDFS_S3_ENDPOINT", "http://fake:8333")
    monkeypatch.setenv("SEAWEEDFS_S3_ACCESS_KEY", "dummy")
    monkeypatch.delenv("SEAWEEDFS_S3_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        from_env()

    assert "SEAWEEDFS_S3_SECRET_KEY" in str(excinfo.value)


def test_from_env_returns_configured_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEAWEEDFS_S3_ENDPOINT", "http://fake:8333")
    monkeypatch.setenv("SEAWEEDFS_S3_ACCESS_KEY", "dummy-access")
    monkeypatch.setenv("SEAWEEDFS_S3_SECRET_KEY", "dummy-secret")
    monkeypatch.setenv("SEAWEEDFS_S3_BUCKET", "dk-data-prestaged")

    store = from_env()
    assert isinstance(store, ObjectStore)
    # Default bucket flows through from env:
    assert store._default_bucket == "dk-data-prestaged"
    # Endpoint is normalized (trailing slash stripped by __init__):
    assert store._endpoint_url == "http://fake:8333"


# ---------------------------------------------------------------------------
# moto-backed fixture — real boto3 client against an in-process S3 server
# ---------------------------------------------------------------------------
@pytest.fixture()
def moto_store(monkeypatch: pytest.MonkeyPatch) -> ObjectStore:
    """ObjectStore wired to a moto-mocked S3 backend."""
    from moto import mock_aws

    ctx = mock_aws()
    ctx.start()

    store = ObjectStore(
        endpoint_url="https://s3.amazonaws.com",
        access_key="testing",
        secret_key="testing",
        region_name="us-east-1",
        default_bucket="dk-data-prestaged",
    )
    # moto intercepts boto3 at the HTTP layer, so the real endpoint_url
    # does not matter — but we set it so nothing accidentally talks to
    # the real AWS even if moto is misconfigured in an environment.
    try:
        yield store
    finally:
        ctx.stop()


# ---------------------------------------------------------------------------
# ensure_bucket idempotency
# ---------------------------------------------------------------------------
def test_ensure_bucket_creates_then_is_idempotent(moto_store: ObjectStore) -> None:
    # First call creates.
    assert moto_store.ensure_bucket("dk-data-prestaged") == "dk-data-prestaged"
    # Second call is a no-op (BucketAlreadyOwnedByYou / BucketAlreadyExists).
    assert moto_store.ensure_bucket("dk-data-prestaged") == "dk-data-prestaged"


def test_ensure_bucket_swallows_already_exists_via_fake_client() -> None:
    """Unit-level check: the ClientError branches swallow only the two
    idempotent codes and propagate everything else.
    """
    store = ObjectStore(
        endpoint_url="http://fake:8333",
        access_key="a",
        secret_key="b",
        default_bucket="dk-data-prestaged",
    )

    fake_client = MagicMock()
    # Case 1: already owned by you — must be swallowed.
    fake_client.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": "yep"}},
        "CreateBucket",
    )
    store._client = fake_client
    assert store.ensure_bucket("some-bucket") == "some-bucket"

    # Case 2: already exists — also swallowed.
    fake_client.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "BucketAlreadyExists", "Message": "yep"}},
        "CreateBucket",
    )
    assert store.ensure_bucket("some-bucket") == "some-bucket"

    # Case 3: any other error — must propagate.
    fake_client.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "nope"}},
        "CreateBucket",
    )
    with pytest.raises(ClientError):
        store.ensure_bucket("some-bucket")


def test_ensure_bucket_rejects_empty_name() -> None:
    store = ObjectStore(
        endpoint_url="http://fake:8333",
        access_key="a",
        secret_key="b",
    )
    with pytest.raises(ValueError):
        store.ensure_bucket("")


# ---------------------------------------------------------------------------
# put_artifact / get_artifact roundtrip
# ---------------------------------------------------------------------------
def test_put_and_get_artifact_roundtrip(
    moto_store: ObjectStore, tmp_path: Path
) -> None:
    moto_store.ensure_bucket("dk-data-prestaged")

    src = tmp_path / "payload.bin"
    payload = b"hello-seaweedfs-" + b"x" * 128
    src.write_bytes(payload)

    returned_key = moto_store.put_artifact(
        local_path=str(src),
        key="prestaged/test/payload.bin",
        content_type="application/octet-stream",
    )
    assert returned_key == "prestaged/test/payload.bin"

    # Roundtrip: download to a fresh path, bytes must match.
    dest = tmp_path / "roundtrip.bin"
    moto_store.get_artifact(key="prestaged/test/payload.bin", local_path=str(dest))
    assert dest.read_bytes() == payload


def test_list_prefix_yields_uploaded_objects(
    moto_store: ObjectStore, tmp_path: Path
) -> None:
    moto_store.ensure_bucket("dk-data-prestaged")
    src = tmp_path / "f.bin"
    src.write_bytes(b"abc")

    for key in ("prestaged/a/1.bin", "prestaged/a/2.bin", "other/3.bin"):
        moto_store.put_artifact(local_path=str(src), key=key)

    keys = sorted(obj["Key"] for obj in moto_store.list_prefix("prestaged/a/"))
    assert keys == ["prestaged/a/1.bin", "prestaged/a/2.bin"]


# ---------------------------------------------------------------------------
# presigned_url shape
# ---------------------------------------------------------------------------
def test_presigned_url_returns_signed_string(moto_store: ObjectStore) -> None:
    moto_store.ensure_bucket("dk-data-prestaged")

    url = moto_store.presigned_url("prestaged/test/payload.bin", expires_in=1800)

    assert isinstance(url, str)
    parsed = urlparse(url)
    assert parsed.scheme in {"http", "https"}
    qs = parse_qs(parsed.query)
    # SigV4 presigned URLs always include these four parameters.
    for expected in (
        "X-Amz-Algorithm",
        "X-Amz-Credential",
        "X-Amz-Date",
        "X-Amz-Expires",
        "X-Amz-Signature",
    ):
        assert expected in qs, f"presigned URL missing {expected}: {qs}"
    assert qs["X-Amz-Expires"] == ["1800"]


# ---------------------------------------------------------------------------
# Consumer-coupling gate: the module MUST NOT hardcode the cluster DNS.
# ---------------------------------------------------------------------------
# Built from parts so this sentinel string itself does not appear as a
# literal anywhere in this file — the gate below can then require zero
# occurrences in the target source files unconditionally.
_CLUSTER_DNS_SENTINEL: str = ".".join(("", "infra", "svc", "cluster", "local"))


def test_no_cluster_dns_in_module_source() -> None:
    module_path = Path(minio_admin.__file__)
    source = module_path.read_text(encoding="utf-8")
    assert _CLUSTER_DNS_SENTINEL not in source, (
        "minio_admin.py must not hardcode a cluster DNS name; the endpoint "
        "comes from SEAWEEDFS_S3_ENDPOINT."
    )


def test_no_cluster_dns_in_test_source() -> None:
    test_path = Path(__file__)
    source = test_path.read_text(encoding="utf-8")
    assert _CLUSTER_DNS_SENTINEL not in source, (
        "tests/unit/test_minio_admin.py must not hardcode a cluster DNS "
        "name; use dummy hosts like 'fake:8333' instead."
    )


def test_endpoint_env_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sanity: from_env honors SEAWEEDFS_S3_ENDPOINT verbatim."""
    monkeypatch.setenv("SEAWEEDFS_S3_ENDPOINT", "http://custom-endpoint:9000/")
    monkeypatch.setenv("SEAWEEDFS_S3_ACCESS_KEY", "a")
    monkeypatch.setenv("SEAWEEDFS_S3_SECRET_KEY", "b")
    store = from_env()
    # Trailing slash stripped but host preserved:
    assert store._endpoint_url == "http://custom-endpoint:9000"


def test_from_env_reads_region_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEAWEEDFS_S3_ENDPOINT", "http://fake:8333")
    monkeypatch.setenv("SEAWEEDFS_S3_ACCESS_KEY", "a")
    monkeypatch.setenv("SEAWEEDFS_S3_SECRET_KEY", "b")
    monkeypatch.setenv("SEAWEEDFS_S3_REGION", "eu-west-1")
    store = from_env()
    assert store._region_name == "eu-west-1"
