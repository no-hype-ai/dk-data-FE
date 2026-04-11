"""Unit tests for build_dsn() — FR-022/FR-023/FR-030 contract.

Feature: 001-silver-medallion-rebuild
Task: T011
"""

import os
import urllib.parse
import pytest

from dk_data.ingestion.utils.database import build_dsn, MissingSecretError


@pytest.fixture(autouse=True)
def _set_required_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-secret")
    monkeypatch.setenv("POSTGRES_USER", "testuser")
    monkeypatch.setenv("POSTGRES_DB", "testdb")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("APPLICATION_NAME", "test-pod")


def _parse_options(dsn: str) -> dict:
    """Parse the `options` query param from a DSN into a dict of GUC→value."""
    parsed = urllib.parse.urlparse(dsn)
    qs = urllib.parse.parse_qs(parsed.query)
    options_str = urllib.parse.unquote(qs.get("options", [""])[0])
    result = {}
    for part in options_str.split(" -c "):
        part = part.strip()
        if part.startswith("-c "):
            part = part[3:]
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


class TestStatementTimeout:
    def test_fetcher_timeout_is_5_min(self):
        dsn = build_dsn()
        options = _parse_options(dsn)
        assert options.get("statement_timeout") == "300000", (
            "Fetcher statement_timeout must be 300000 ms (5 min) per FR-021c"
        )

    def test_long_running_timeout_is_10_min(self):
        dsn = build_dsn(is_long_running=True)
        options = _parse_options(dsn)
        assert options.get("statement_timeout") == "600000", (
            "Long-running statement_timeout must be 600000 ms (10 min) per FR-021c"
        )


class TestIdleTimeout:
    def test_idle_in_transaction_is_5_min(self):
        dsn = build_dsn()
        options = _parse_options(dsn)
        assert options.get("idle_in_transaction_session_timeout") == "300000", (
            "idle_in_transaction_session_timeout must be 300000 ms per FR-021d"
        )


class TestLockTimeout:
    def test_lock_timeout_is_set(self):
        dsn = build_dsn()
        options = _parse_options(dsn)
        assert options.get("lock_timeout") == "30000", (
            "lock_timeout must be 30000 ms (30 s) per FR-022"
        )


class TestApplicationName:
    def test_application_name_from_env(self, monkeypatch):
        monkeypatch.setenv("APPLICATION_NAME", "my-fetcher-pod")
        dsn = build_dsn()
        options = _parse_options(dsn)
        assert options.get("application_name") == "my-fetcher-pod", (
            "application_name must come from APPLICATION_NAME env (FR-023)"
        )

    def test_application_name_override(self):
        dsn = build_dsn(application_name="custom-name")
        options = _parse_options(dsn)
        assert options.get("application_name") == "custom-name"


class TestKeepalives:
    def test_keepalives_enabled(self):
        dsn = build_dsn()
        assert "keepalives=1" in dsn, "TCP keepalives must be enabled (FR-022)"
        assert "keepalives_idle=60" in dsn
        assert "keepalives_interval=10" in dsn
        assert "keepalives_count=5" in dsn


class TestPgBouncerRouting:
    def test_default_uses_pgbouncer(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST", "pgbouncer.infra.svc.cluster.local")
        monkeypatch.delenv("POSTGRES_HOST_DIRECT", raising=False)
        dsn = build_dsn()
        assert "pgbouncer.infra.svc.cluster.local" in dsn, (
            "Default connections must route through PgBouncer (FR-024)"
        )

    def test_direct_connection_bypasses_pgbouncer(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_HOST_DIRECT", "postgres.infra.svc.cluster.local")
        dsn = build_dsn(use_pgbouncer=False)
        assert "postgres.infra.svc.cluster.local" in dsn, (
            "is_long_running=True must use POSTGRES_HOST_DIRECT (FR-037b)"
        )


class TestMissingSecret:
    def test_raises_on_missing_password(self, monkeypatch):
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        with pytest.raises(MissingSecretError):
            build_dsn()

    def test_raises_on_placeholder_password(self, monkeypatch):
        monkeypatch.setenv("POSTGRES_PASSWORD", "changeme")
        with pytest.raises(MissingSecretError):
            build_dsn()


class TestDsnStructure:
    def test_dsn_is_postgresql_url(self):
        dsn = build_dsn()
        assert dsn.startswith("postgresql://"), "DSN must be a libpq URI"

    def test_dsn_contains_dbname(self):
        dsn = build_dsn()
        assert "/testdb" in dsn

    def test_dsn_contains_user(self):
        dsn = build_dsn()
        assert "testuser" in dsn
