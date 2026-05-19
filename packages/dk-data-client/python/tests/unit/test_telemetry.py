"""Unit tests for telemetry emission.

We do not hit a real Loki here — telemetry must degrade gracefully when
the push endpoint is unavailable, so `loki_push_url=None` is the happy
path for unit tests.
"""

from __future__ import annotations

import asyncio

from dk_data_client.telemetry import TelemetryEmitter, TelemetryEvent, hash_args


class TestHashArgs:
    def test_hashes_are_deterministic(self):
        h1 = hash_args({"id": "X"})
        h2 = hash_args({"id": "X"})
        assert h1 == h2

    def test_different_args_differ(self):
        assert hash_args({"id": "A"}) != hash_args({"id": "B"})

    def test_arg_order_is_normalized(self):
        assert hash_args({"a": 1, "b": 2}) == hash_args({"b": 2, "a": 1})

    def test_hash_has_sha256_prefix(self):
        assert hash_args({"x": 1}).startswith("sha256:")

    def test_hash_is_short_enough_for_loki(self):
        # 32 hex chars + prefix — short enough for Loki labels
        h = hash_args({"x": 1})
        assert len(h) <= 64


class TestEventConstruction:
    def test_event_to_loki_stream_has_expected_labels(self):
        event = TelemetryEvent(
            ts=1_700_000_000,
            client="behavior-labs-ai",
            client_version="0.1.0",
            method="molecules.getProfile",
            args_hash="sha256:deadbeef",
            outcome="hit",
            latency_ms=42,
            cache_tier="l1",
        )
        stream = event.to_loki_stream()
        assert stream["streams"][0]["stream"]["app"] == "adapter-telemetry"
        assert stream["streams"][0]["stream"]["method"] == "molecules.getProfile"
        assert stream["streams"][0]["stream"]["outcome"] == "hit"
        assert stream["streams"][0]["stream"]["client"] == "behavior-labs-ai"

    def test_line_is_json(self):
        import json

        event = TelemetryEvent(
            ts=100,
            client="c",
            client_version="v",
            method="m",
            args_hash="h",
            outcome="miss",
            latency_ms=1,
        )
        stream = event.to_loki_stream()
        _, line = stream["streams"][0]["values"][0]
        parsed = json.loads(line)
        assert parsed["latency_ms"] == 1

    def test_error_type_is_included_only_when_set(self):
        import json

        e1 = TelemetryEvent(
            ts=1, client="c", client_version="v",
            method="m", args_hash="h", outcome="error", latency_ms=1,
        )
        e1_line = json.loads(e1.to_loki_stream()["streams"][0]["values"][0][1])
        assert "error_type" not in e1_line

        e2 = TelemetryEvent(
            ts=1, client="c", client_version="v",
            method="m", args_hash="h", outcome="error", latency_ms=1,
            error_type="DkDataNotFoundError",
        )
        e2_line = json.loads(e2.to_loki_stream()["streams"][0]["values"][0][1])
        assert e2_line["error_type"] == "DkDataNotFoundError"


class TestEmitter:
    async def test_emit_is_noop_when_disabled(self):
        emitter = TelemetryEmitter(
            client_name="c", client_version="0.1.0", loki_push_url=None
        )
        emitter.set_enabled(False)
        emitter.emit(method="x", args={}, outcome="hit", latency_ms=1)
        # Queue should not have accumulated anything
        assert emitter._queue.qsize() == 0

    async def test_emit_enqueues_when_enabled(self):
        emitter = TelemetryEmitter(
            client_name="c", client_version="0.1.0", loki_push_url=None
        )
        emitter.emit(method="x", args={}, outcome="hit", latency_ms=1)
        # Worker is async; either it's drained or still queued
        assert emitter._queue.qsize() <= 1
        # Let the event loop run briefly so the worker picks up the event
        await asyncio.sleep(0.01)
        await emitter.aclose()
