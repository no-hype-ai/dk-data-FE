"""Structured telemetry emission for dk-data-client.

Every client call emits exactly one event describing:

- which method was called (e.g., "molecules.getProfile")
- content-addressed `args_hash` (NOT the raw args — never log PII/PHI)
- outcome: hit | miss | stale | fallthrough_upstream | fallthrough_hydrate | error
- latency_ms
- cache_tier: l1 | l2 | none
- client_version and dk_data_version

Events ship to Loki via an HTTP push endpoint (Grafana Cloud Loki API).
If the push endpoint is unavailable, events are dropped silently —
telemetry is best-effort and must NEVER block or fail the primary call.

The emitter is async and fire-and-forget. On client close, the emitter
flushes any pending events (up to a short timeout).

Invariants enforced here:
- No tokens, API keys, or response bodies in the event payload
- No raw argument values — only the sha256 hash
- No PII/PHI
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger("dk_data_client.telemetry")

Outcome = Literal[
    "hit",
    "miss",
    "stale",
    "fallthrough_upstream",
    "fallthrough_hydrate",
    "error",
]
CacheTier = Literal["l1", "l2", "none"]


@dataclass
class TelemetryEvent:
    """One telemetry event per client call.

    See contracts/client-package-api.md → "Telemetry event schema".
    Field names match the TS client exactly so Loki queries are portable
    between language implementations.
    """

    ts: int
    client: str
    client_version: str
    method: str
    args_hash: str
    outcome: Outcome
    latency_ms: int
    dk_data_version: str = ""
    cache_tier: CacheTier = "none"
    error_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_loki_stream(self) -> dict[str, Any]:
        """Convert to the Loki push payload format.

        Loki expects `{streams: [{stream: {labels}, values: [[ns, line]]}]}`.
        We keep the stream labels small (client, method, outcome) and
        ship everything else in the line as JSON so Grafana's `| json`
        filter can unpack it.
        """
        labels = {
            "app": "adapter-telemetry",
            "client": self.client,
            "method": self.method,
            "outcome": self.outcome,
        }
        line_payload = {
            "ts": self.ts,
            "client_version": self.client_version,
            "args_hash": self.args_hash,
            "latency_ms": self.latency_ms,
            "cache_tier": self.cache_tier,
            "dk_data_version": self.dk_data_version,
        }
        if self.error_type:
            line_payload["error_type"] = self.error_type
        if self.extra:
            line_payload["extra"] = self.extra
        ns_timestamp = str(int(self.ts * 1_000_000_000))
        return {
            "streams": [
                {
                    "stream": labels,
                    "values": [[ns_timestamp, json.dumps(line_payload, default=str)]],
                }
            ]
        }


def hash_args(args: dict[str, Any]) -> str:
    """sha256(canonicalized args) — NEVER log the raw args themselves."""
    payload = json.dumps(args, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class TelemetryEmitter:
    """Fire-and-forget telemetry emitter.

    Events are queued and flushed asynchronously. A failure to push
    events (network error, Loki down, misconfigured URL) is logged at
    DEBUG level and then swallowed — telemetry must never break calls.
    """

    def __init__(
        self,
        *,
        client_name: str,
        client_version: str,
        loki_push_url: str | None = None,
        dk_data_version: str = "",
        enabled: bool = True,
        queue_max_size: int = 256,
    ) -> None:
        self._client_name = client_name
        self._client_version = client_version
        self._loki_push_url = loki_push_url
        self._dk_data_version = dk_data_version
        self._enabled = enabled
        self._queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=queue_max_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._http: httpx.AsyncClient | None = None

    def set_enabled(self, enabled: bool) -> None:
        """Public opt-out hook for tests and privacy-sensitive consumers."""
        self._enabled = enabled

    def set_dk_data_version(self, version: str) -> None:
        """Called by the client after a `serverInfo()` lookup."""
        self._dk_data_version = version

    def emit(
        self,
        *,
        method: str,
        args: dict[str, Any],
        outcome: Outcome,
        latency_ms: int,
        cache_tier: CacheTier = "none",
        error_type: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Enqueue one event. Non-blocking.

        If telemetry is disabled, or the queue is full, the event is
        dropped silently. This is by design — no amount of telemetry
        pressure can stall the primary call.
        """
        if not self._enabled:
            return
        event = TelemetryEvent(
            ts=int(time.time()),
            client=self._client_name,
            client_version=self._client_version,
            method=method,
            args_hash=hash_args(args),
            outcome=outcome,
            latency_ms=latency_ms,
            dk_data_version=self._dk_data_version,
            cache_tier=cache_tier,
            error_type=error_type,
            extra=extra or {},
        )
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("telemetry queue full — dropping event")
            return
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        """Drain the queue, pushing batches to Loki."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=5.0)
        # Drain until the queue is empty to keep memory bounded.
        while True:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                return
            await self._push(event)

    async def _push(self, event: TelemetryEvent) -> None:
        if not self._loki_push_url:
            # Structured log only — consumers running without a Loki URL
            # still see the events in their own log pipeline.
            logger.debug("telemetry: %s", json.dumps(asdict(event), default=str))
            return
        assert self._http is not None
        try:
            response = await self._http.post(
                self._loki_push_url,
                json=event.to_loki_stream(),
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                logger.debug(
                    "telemetry push got HTTP %d: %s",
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError as e:
            logger.debug("telemetry push failed: %s", e)

    async def aclose(self) -> None:
        """Drain the queue with a 1-second budget, then close the HTTP client."""
        if self._worker_task is not None:
            try:
                await asyncio.wait_for(self._worker_task, timeout=1.0)
            except TimeoutError:
                self._worker_task.cancel()
        if self._http is not None:
            await self._http.aclose()
