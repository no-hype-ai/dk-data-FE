"""Non-blocking audit log writer for the metering proxy.

Feature: 002-external-integration-foundation (US-3, FR-015, T024a/b/b1)

Every request that reaches the proxy produces one audit record:

    consumer_id, resource (path + schema), status, latency_ms,
    method, ts (wall clock), request_id

Records are pushed into an asyncio.Queue from the hot path (never
blocking the request). A single background worker drains the queue
and fan-writes to the configured sink(s):

  - **loki** (default, production): HTTP push to Loki under
    `app=metering-proxy-audit`. Failures are counted in a drop metric
    and swallowed — audit must NEVER block.
  - **postgres**: INSERT into `meta.api_audit_log` (reuses the table
    created by feature 013-observability-governance). Intended for
    consumers that want a queryable audit trail alongside Loki.
  - **stdout**: JSON lines to stdout for local dev.

Backpressure policy: if the queue fills (default 1024 events), the
OLDEST record is dropped and a counter is incremented. This is the
right tradeoff for audit — we'd rather lose the oldest event than
stall a consumer request.

T024b1 requirement: the writer MUST be async and non-blocking.
Verified by `tests/metering_proxy/test_audit_log.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger("dk_data.metering_proxy.audit")

AuditSink = Literal["loki", "postgres", "stdout", "disabled"]


@dataclass
class AuditRecord:
    ts: float
    consumer_id: str
    method: str
    path: str
    schema: str
    status_code: int
    latency_ms: int
    request_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json_line(self) -> str:
        payload = asdict(self)
        payload["ts_iso"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.ts)
        )
        return json.dumps(payload, default=str)

    def to_loki_stream(self) -> dict[str, Any]:
        labels = {
            "app": "metering-proxy-audit",
            "consumer": self.consumer_id,
            "method": self.method,
            "status": str(self.status_code),
        }
        line = {
            "ts": self.ts,
            "path": self.path,
            "schema": self.schema,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
        }
        if self.extra:
            line["extra"] = self.extra
        ns = str(int(self.ts * 1_000_000_000))
        return {
            "streams": [
                {"stream": labels, "values": [[ns, json.dumps(line, default=str)]]}
            ]
        }


class AuditWriter:
    """Async fire-and-forget audit log writer.

    Usage:

        writer = AuditWriter(sink="loki", loki_push_url=...)
        await writer.start()
        writer.emit(consumer_id="blai", path="/molecules", ...)
        # ... later
        await writer.stop()

    The writer owns its own asyncio task. `emit()` is a plain sync call
    that never blocks — it pushes onto an asyncio.Queue. If the queue
    is full, the oldest record is dropped and `dropped_total` is
    incremented.
    """

    def __init__(
        self,
        *,
        sink: AuditSink | None = None,
        loki_push_url: str | None = None,
        queue_size: int = 1024,
        stdout_fallback: bool = True,
    ) -> None:
        # Env override so operators can flip the sink without a code deploy.
        resolved_sink: AuditSink
        if sink is not None:
            resolved_sink = sink
        else:
            resolved_sink = os.getenv("METERING_PROXY_AUDIT_SINK", "loki")  # type: ignore[assignment]
        self.sink: AuditSink = resolved_sink
        self.loki_push_url: str | None = (
            loki_push_url or os.getenv("METERING_PROXY_AUDIT_LOKI_URL")
        )
        self._queue: asyncio.Queue[AuditRecord] = asyncio.Queue(maxsize=queue_size)
        self._stdout_fallback = stdout_fallback
        self._worker: asyncio.Task[None] | None = None
        self._stopped = False
        self.dropped_total: int = 0
        self.emitted_total: int = 0

    async def start(self) -> None:
        if self._worker is None and not self._stopped:
            self._worker = asyncio.create_task(self._run(), name="audit-writer")

    async def stop(self, *, drain_timeout: float = 1.0) -> None:
        self._stopped = True
        if self._worker is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=drain_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "audit queue drain timeout — dropping %d pending records",
                self._queue.qsize(),
            )
        self._worker.cancel()
        try:
            await self._worker
        except (asyncio.CancelledError, Exception):
            pass
        self._worker = None

    def emit(
        self,
        *,
        consumer_id: str,
        method: str,
        path: str,
        schema: str,
        status_code: int,
        latency_ms: int,
        request_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._stopped:
            return
        record = AuditRecord(
            ts=time.time(),
            consumer_id=consumer_id,
            method=method,
            path=path,
            schema=schema,
            status_code=status_code,
            latency_ms=latency_ms,
            request_id=request_id,
            extra=extra or {},
        )
        self.emitted_total += 1
        if self.sink == "disabled":
            # Count as emitted (so callers and tests can verify the
            # hot path ran) but don't touch the queue at all.
            return
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            # Drop the oldest and enqueue the new one. If the drop
            # itself raises (queue empty race), swallow it — we tried.
            try:
                _ = self._queue.get_nowait()
                self._queue.task_done()
                self._queue.put_nowait(record)
            except Exception:
                pass
            self.dropped_total += 1

    async def _run(self) -> None:
        while not self._stopped:
            try:
                record = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._write(record)
            except Exception as e:  # noqa: BLE001
                logger.debug("audit write failed: %s", e)
            finally:
                self._queue.task_done()

    async def _write(self, record: AuditRecord) -> None:
        if self.sink == "stdout":
            print(record.to_json_line(), flush=True)
            return
        if self.sink == "loki":
            await self._write_loki(record)
            return
        if self.sink == "postgres":
            await self._write_postgres(record)
            return

    async def _write_loki(self, record: AuditRecord) -> None:
        if not self.loki_push_url:
            if self._stdout_fallback:
                print(record.to_json_line(), flush=True)
            return
        try:
            import httpx
        except ImportError:  # pragma: no cover
            if self._stdout_fallback:
                print(record.to_json_line(), flush=True)
            return
        async with httpx.AsyncClient(timeout=2.0) as http:
            try:
                response = await http.post(
                    self.loki_push_url,
                    json=record.to_loki_stream(),
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code >= 400:
                    logger.debug(
                        "audit loki push returned %d", response.status_code
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug("audit loki push error: %s", e)

    async def _write_postgres(self, record: AuditRecord) -> None:
        """Best-effort Postgres write via dk_data.db helpers.

        If the Postgres path fails (e.g. connection lost), we log at
        DEBUG and drop the record — audit must never cascade into a
        request failure.
        """
        try:
            # Lazy import so unit tests don't need the DB stack
            from dk_data.db import get_pool  # type: ignore[attr-defined]
        except Exception:
            if self._stdout_fallback:
                print(record.to_json_line(), flush=True)
            return
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO meta.api_audit_log
                        (request_id, timestamp, source, method, path,
                         user_role, status_code, response_time_ms,
                         action, category, details)
                    VALUES
                        ($1, to_timestamp($2), 'metering-proxy', $3, $4,
                         $5, $6, $7, 'proxy', 'access', $8::jsonb)
                    """,
                    record.request_id or None,
                    record.ts,
                    record.method,
                    record.path,
                    record.consumer_id,
                    record.status_code,
                    record.latency_ms,
                    json.dumps(
                        {"schema": record.schema, **record.extra}, default=str
                    ),
                )
        except Exception as e:  # noqa: BLE001
            logger.debug("audit postgres write error: %s", e)
