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
