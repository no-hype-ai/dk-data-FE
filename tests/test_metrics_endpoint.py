"""
Metrics Endpoint Verification Tests
Feature: 013-observability-governance (US1)
Task: T002

Verifies that all 10 metric families defined in src/dk_data/observability/metrics.py
are properly registered with the prometheus_client registry, with correct names,
types, and label sets.
"""

import pytest
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    REGISTRY,
)


# -----------------------------------------------------------------------
# Expected metric families — source of truth per metrics.py
# -----------------------------------------------------------------------

EXPECTED_METRICS = {
    "http_requests_total": {
        "type": Counter,
        "labels": ["method", "path", "status"],
    },
    "http_request_duration_seconds": {
        "type": Histogram,
        "labels": ["method", "path"],
    },
    "db_query_duration_seconds": {
        "type": Histogram,
        "labels": ["query_type"],
    },
    "batch_job_duration_seconds": {
        "type": Histogram,
        "labels": ["job_name"],
    },
    "batch_job_records_processed": {
        "type": Counter,
        "labels": ["job_name"],
    },
    "batch_job_failures_total": {
        "type": Counter,
        "labels": ["job_name"],
    },
    "batch_job_last_success_timestamp": {
        "type": Gauge,
        "labels": ["job_name"],
    },
    "dk_data_source_last_refresh_timestamp": {
        "type": Gauge,
        "labels": ["source_id", "source_name"],
    },
    "dk_data_source_row_count": {
        "type": Gauge,
        "labels": ["source_id", "source_name"],
    },
    "dk_data_source_staleness_hours": {
        "type": Gauge,
        "labels": ["source_id", "source_name"],
    },
}


class TestMetricFamiliesRegistered:
    """Verify all 10 metric families are present in the default registry."""

    @pytest.fixture(autouse=True)
    def _import_metrics(self):
        """Import the metrics module to trigger registration."""
        import dk_data.observability.metrics  # noqa: F401

    def _get_registered_names(self) -> set[str]:
        """Collect all metric family names from the default registry.

        Note: prometheus_client strips the ``_total`` suffix from Counter
        family names in the Python registry (OpenMetrics convention).  We
        collect both the raw name and the ``<name>_total`` variant so
        look-ups work regardless of suffix convention.
        """
        names: set[str] = set()
        for m in REGISTRY.collect():
            names.add(m.name)
            names.add(m.name + "_total")
        return names

    def test_exactly_10_expected_families(self):
        """Spec requires exactly 10 metric families."""
        assert len(EXPECTED_METRICS) == 10

    @pytest.mark.parametrize("metric_name", sorted(EXPECTED_METRICS.keys()))
    def test_metric_registered(self, metric_name):
        """Each expected metric must be present in the default registry."""
        registered = self._get_registered_names()
        assert metric_name in registered, (
            f"Metric '{metric_name}' not found in registry. "
            f"Registered: {sorted(registered)}"
        )


class TestMetricTypes:
    """Verify each metric is the correct Prometheus type."""

    @pytest.fixture(autouse=True)
    def _import_metrics(self):
        import dk_data.observability.metrics as m
        self.mod = m

    def test_http_requests_total_is_counter(self):
        assert isinstance(self.mod.HTTP_REQUESTS_TOTAL, Counter)

    def test_http_request_duration_is_histogram(self):
        assert isinstance(self.mod.HTTP_REQUEST_DURATION_SECONDS, Histogram)

    def test_db_query_duration_is_histogram(self):
        assert isinstance(self.mod.DB_QUERY_DURATION_SECONDS, Histogram)

    def test_batch_job_duration_is_histogram(self):
        assert isinstance(self.mod.BATCH_JOB_DURATION_SECONDS, Histogram)

    def test_batch_job_records_is_counter(self):
        assert isinstance(self.mod.BATCH_JOB_RECORDS_PROCESSED, Counter)

    def test_batch_job_failures_is_counter(self):
        assert isinstance(self.mod.BATCH_JOB_FAILURES_TOTAL, Counter)

    def test_batch_job_last_success_is_gauge(self):
        assert isinstance(self.mod.BATCH_JOB_LAST_SUCCESS_TIMESTAMP, Gauge)

    def test_source_last_refresh_is_gauge(self):
        assert isinstance(self.mod.DATA_SOURCE_LAST_REFRESH_TIMESTAMP, Gauge)

    def test_source_row_count_is_gauge(self):
        assert isinstance(self.mod.DATA_SOURCE_ROW_COUNT, Gauge)

    def test_source_staleness_is_gauge(self):
        assert isinstance(self.mod.DATA_SOURCE_STALENESS_HOURS, Gauge)


class TestMetricLabels:
    """Verify each metric has the expected label names."""

    @pytest.fixture(autouse=True)
    def _import_metrics(self):
        import dk_data.observability.metrics as m
        self.mod = m

    def test_http_requests_total_labels(self):
        assert self.mod.HTTP_REQUESTS_TOTAL._labelnames == (
            "method", "path", "status",
        )

    def test_http_request_duration_labels(self):
        assert self.mod.HTTP_REQUEST_DURATION_SECONDS._labelnames == (
            "method", "path",
        )

    def test_db_query_duration_labels(self):
        assert self.mod.DB_QUERY_DURATION_SECONDS._labelnames == ("query_type",)

    def test_batch_job_duration_labels(self):
        assert self.mod.BATCH_JOB_DURATION_SECONDS._labelnames == ("job_name",)

    def test_batch_job_records_labels(self):
        assert self.mod.BATCH_JOB_RECORDS_PROCESSED._labelnames == ("job_name",)

    def test_batch_job_failures_labels(self):
        assert self.mod.BATCH_JOB_FAILURES_TOTAL._labelnames == ("job_name",)

    def test_batch_job_last_success_labels(self):
        assert self.mod.BATCH_JOB_LAST_SUCCESS_TIMESTAMP._labelnames == ("job_name",)

    def test_source_last_refresh_labels(self):
        assert self.mod.DATA_SOURCE_LAST_REFRESH_TIMESTAMP._labelnames == (
            "source_id", "source_name",
        )

    def test_source_row_count_labels(self):
        assert self.mod.DATA_SOURCE_ROW_COUNT._labelnames == (
            "source_id", "source_name",
        )

    def test_source_staleness_labels(self):
        assert self.mod.DATA_SOURCE_STALENESS_HOURS._labelnames == (
            "source_id", "source_name",
        )


class TestMetricsOutput:
    """Verify the /metrics endpoint helper produces valid output."""

    @pytest.fixture(autouse=True)
    def _import_metrics(self):
        import dk_data.observability.metrics as m
        self.mod = m

    def test_get_metrics_returns_bytes(self):
        output = self.mod.get_metrics()
        assert isinstance(output, bytes)
        assert len(output) > 0

    def test_get_metrics_content_type(self):
        ct = self.mod.get_metrics_content_type()
        assert "text/plain" in ct or "text/openmetrics" in ct

    def test_output_contains_all_metric_names(self):
        output = self.mod.get_metrics().decode("utf-8")
        for name in EXPECTED_METRICS:
            assert name in output, f"Metric '{name}' not in /metrics output"
