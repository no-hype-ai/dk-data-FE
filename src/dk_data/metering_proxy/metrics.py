"""Prometheus metrics for the metering proxy sidecar.

Metric Naming Convention:
- dk_data_metering_  — metering-proxy specific metrics

Exposed on /metrics (port 3001, the proxy port) for Prometheus scraping.
"""

from prometheus_client import Counter, Gauge, Histogram

# Request counters
REQUESTS_TOTAL = Counter(
    "dk_data_metering_requests_total",
    "Total requests through metering proxy",
    ["consumer", "schema", "method", "status"],
)

# Response size tracking
RESPONSE_BYTES_TOTAL = Counter(
    "dk_data_metering_response_bytes_total",
    "Total response bytes through metering proxy",
    ["consumer", "schema"],
)

# Request latency
REQUEST_DURATION_SECONDS = Histogram(
    "dk_data_metering_request_duration_seconds",
    "Request duration through metering proxy",
    ["consumer", "schema"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Rate limiting
RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "dk_data_metering_rate_limit_rejections_total",
    "Total rate-limited requests per consumer",
    ["consumer"],
)

# Active consumers gauge
ACTIVE_CONSUMERS = Gauge(
    "dk_data_metering_active_consumers",
    "Number of distinct consumers that have made requests",
)

# Auth failures
AUTH_FAILURES_TOTAL = Counter(
    "dk_data_metering_auth_failures_total",
    "Total authentication failures",
    ["reason"],
)

# Schema access denied
SCHEMA_ACCESS_DENIED_TOTAL = Counter(
    "dk_data_metering_schema_access_denied_total",
    "Total schema access denied events",
    ["consumer", "schema"],
)

# Per-consumer in-flight request count (drives the 503 load-shed alert)
IN_FLIGHT_REQUESTS = Gauge(
    "dk_data_metering_in_flight_requests",
    "Current in-flight requests per consumer",
    ["consumer"],
)

# 503 load-shed events (consumer hit max_in_flight)
LOAD_SHED_TOTAL = Counter(
    "dk_data_metering_load_shed_total",
    "Total requests rejected with 503 because the consumer hit max_in_flight",
    ["consumer"],
)

# -----------------------------------------------------------------------------
# Feature 003 — JWT minting (issue #283)
# -----------------------------------------------------------------------------

# Successful JWT mint + inject, labeled by consumer tier. One increment
# per request that reaches PostgREST with a valid Bearer JWT. Bound to
# a Grafana dashboard panel (grafana/dashboards/dk-data-adapter-telemetry.json)
# and an alert rule (grafana/alerts/dk-data.yaml) — the three-way binding
# required by .dk/memory/principles.md rule #6.
JWT_MINTED_TOTAL = Counter(
    "dk_data_metering_jwt_minted_total",
    "JWTs minted and injected into forwarded requests, by consumer tier",
    ["tier"],
)

# Mint failures. Expected steady-state: zero. A non-zero rate means the
# proxy is 500-ing requests — either a misconfigured tier, a missing
# secret at runtime, or a code bug. Labels match JWTMintError.error_type.
JWT_MINT_ERRORS_TOTAL = Counter(
    "dk_data_metering_jwt_mint_errors_total",
    "JWT mint failures, by error type (expected steady-state: 0)",
    ["error_type"],
)

# FR-010: safety counter for any forward path that does NOT mint a JWT.
# Steady-state is zero — a non-zero value means a request reached
# PostgREST without a Bearer JWT, which would land as the anonymous
# role (dk_data_no_anon with zero grants). This is a bug-detector, not
# a normal-operation metric. Bound to a dashboard panel and an alert.
REQUESTS_FORWARDED_WITHOUT_JWT_TOTAL = Counter(
    "dk_data_metering_requests_forwarded_without_jwt_total",
    "Requests forwarded to PostgREST without a minted JWT "
    "(steady-state: 0; any non-zero value is a bug)",
)
