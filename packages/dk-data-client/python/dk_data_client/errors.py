"""Typed error hierarchy for dk-data-client.

Every HTTP failure path from the server is translated into one of these
exceptions so consumers can branch on type, not on status code.

Maps:
    401 -> DkDataAuthError       (missing/invalid JWT)
    403 -> DkDataForbiddenError  (schema not in consumer allowlist)
    404 -> DkDataNotFoundError   (resource not present)
    410 -> DkDataStaleError      (resource exists but marked stale)
    429 -> DkDataRateLimitError  (metering proxy rate limit)
    5xx -> DkDataServerError

Upstream fallback failures surface as DkDataUpstreamError regardless of
the upstream's own status code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class DkDataError(Exception):
    """Base class for every dk-data-client error.

    All client errors inherit from this — catching DkDataError catches
    every failure mode the client can surface (including wrapped
    transport and auth errors).
    """

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = details or {}


class DkDataAuthError(DkDataError):
    """401 — missing, malformed, expired, or otherwise-invalid JWT.

    See docs/runbooks/metering-proxy-401-debug.md for triage.
    """


class DkDataForbiddenError(DkDataError):
    """403 — valid JWT but consumer is not allowed to read the target schema.

    The proxy enforces `allowed_schemas` per consumer from consumers.yaml.
    Fix: edit consumers.yaml and roll the proxy.
    """


class DkDataNotFoundError(DkDataError):
    """404 — the resource does not exist in dk-data.

    This is NOT the same as the upstream not having the resource. In
    strict fallback mode this is a hard failure; in upstream mode the
    client will try the upstream source before raising.
    """


class DkDataStaleError(DkDataError):
    """410 — the resource exists but is marked stale.

    Gold tables emit a staleness gauge; if the freshness exceeds the
    documented SLA the server returns 410 with a `last_refreshed_at`
    hint so the consumer can decide whether to accept the stale data.
    """

    def __init__(
        self,
        message: str,
        *,
        last_refreshed_at: datetime,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.last_refreshed_at = last_refreshed_at


class DkDataUpstreamError(DkDataError):
    """Fallback to upstream failed.

    Raised only when `fallback_mode="upstream"` and the upstream source
    (PubChem, FDA, CT.gov, Europe PMC, etc.) itself returned an error.
    """

    def __init__(
        self,
        message: str,
        *,
        upstream: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.upstream = upstream


class DkDataRateLimitError(DkDataError):
    """429 — the metering proxy rate-limited this consumer.

    `retry_after` is the number of seconds the consumer should wait
    before retrying (parsed from the Retry-After response header).
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after = retry_after


class DkDataServerError(DkDataError):
    """5xx — dk-data is broken.

    Check metrics + logs for the specific failure mode. The client will
    NOT retry 5xx automatically in v0.1 (explicit, observable failures
    are better than silent retry storms).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.status_code = status_code
