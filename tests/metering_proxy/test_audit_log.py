"""T024a/T024b/T024b1 — Metering proxy writes an audit log for every
request, asynchronously, without blocking the hot path.

Feature: 002-external-integration-foundation (US-3, FR-015)
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dk_data.metering_proxy import app as app_module
from dk_data.metering_proxy.audit import AuditRecord, AuditWriter


class TestAuditRecordSerialization:
    def test_json_line_is_parseable(self):
        record = AuditRecord(
            ts=1_700_000_000.0,
            consumer_id="blai",
            method="GET",
            path="/mol_silver/molecules",
            schema="mol_silver",
            status_code=200,
            latency_ms=42,
            request_id="abc123",
        )
        import json

        parsed = json.loads(record.to_json_line())
        assert parsed["consumer_id"] == "blai"
        assert parsed["status_code"] == 200
        assert parsed["latency_ms"] == 42
        assert parsed["ts_iso"].startswith("2023-") or parsed["ts_iso"].startswith("202")

    def test_loki_stream_has_expected_labels(self):
        record = AuditRecord(
            ts=1_700_000_000.0,
            consumer_id="dkos",
            method="POST",
            path="/rpc/resolve_molecule",
            schema="api",
            status_code=200,
            latency_ms=12,
        )
        stream = record.to_loki_stream()
        labels = stream["streams"][0]["stream"]
        assert labels["app"] == "metering-proxy-audit"
        assert labels["consumer"] == "dkos"
        assert labels["method"] == "POST"
        assert labels["status"] == "200"


class TestAuditWriterBackpressure:
    """T024b1: writes must be non-blocking; a full queue drops the
    oldest record rather than stalling the hot path."""

    @pytest.mark.asyncio
    async def test_emit_is_non_blocking(self):
        writer = AuditWriter(sink="disabled", queue_size=4)
        await writer.start()
        start = time.perf_counter()
        for _ in range(200):
            writer.emit(
                consumer_id="x",
                method="GET",
                path="/p",
                schema="api",
                status_code=200,
                latency_ms=1,
            )
        elapsed = time.perf_counter() - start
        # 200 emits must take well under 50 ms even with a tiny queue
        assert elapsed < 0.05, f"emit loop took {elapsed*1000:.1f} ms"
        await writer.stop()

    @pytest.mark.asyncio
    async def test_full_queue_drops_oldest(self):
        # Use stdout sink with a tiny queue and NEVER call start() so
        # the worker never drains and the queue stays at capacity.
        writer = AuditWriter(sink="stdout", queue_size=4)
        for i in range(10):
            writer.emit(
                consumer_id=str(i),
                method="GET",
                path="/p",
                schema="api",
                status_code=200,
                latency_ms=1,
            )
        # 10 emits into a 4-size queue → at least 6 drops.
        assert writer.dropped_total >= 6

    @pytest.mark.asyncio
    async def test_stopped_writer_is_noop(self):
        writer = AuditWriter(sink="disabled", queue_size=4)
        await writer.stop()
        writer.emit(
            consumer_id="x",
            method="GET",
            path="/p",
            schema="api",
            status_code=200,
            latency_ms=1,
        )
        assert writer.emitted_total == 0


class TestProxyEmitsAudit:
    """End-to-end: each proxy response produces exactly one audit emit."""

    def test_successful_request_increments_emitted_total(self, client, monkeypatch):
        # Replace the real (stopped) audit writer with a fresh one so
        # we can count emits deterministically.
        writer = AuditWriter(sink="disabled")
        monkeypatch.setattr(app_module, "audit_writer", writer)
        client.get(
            "/mol_silver/molecules",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert writer.emitted_total == 1

    def test_auth_failure_still_produces_audit_record(self, client, monkeypatch):
        writer = AuditWriter(sink="disabled")
        monkeypatch.setattr(app_module, "audit_writer", writer)
        client.get("/mol_silver/molecules")
        assert writer.emitted_total == 1

    def test_schema_denial_produces_audit_record(self, client, monkeypatch):
        writer = AuditWriter(sink="disabled")
        monkeypatch.setattr(app_module, "audit_writer", writer)
        client.get(
            "/hcs_silver/providers",
            headers={"Authorization": "Bearer dk_data_blai_test_key"},
        )
        assert writer.emitted_total == 1
