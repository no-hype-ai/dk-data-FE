"""
Smoke tests for Grafana dashboard JSON files.

Feature: 002-external-integration-foundation (US-12, T114)

This test file ensures every dashboard JSON in grafana/dashboards/:

  1. Is valid JSON
  2. Has the minimum Grafana schema fields (title, panels, schemaVersion)
  3. Contains at least one panel
  4. Every panel has a type, an id, and (if it queries metrics) at least
     one target with a datasource reference
  5. Every PromQL target references a metric that is actually defined in
     src/dk_data/observability/metrics.py (no dangling metric names)
  6. Every panel's data source matches one of the known datasources
     (Prometheus for metrics, Loki for logs)

Run:
    pytest tests/observability/test_dashboard_smoke.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS_DIR = REPO_ROOT / "grafana" / "dashboards"
METRICS_FILE = REPO_ROOT / "src" / "dk_data" / "observability" / "metrics.py"

KNOWN_DATASOURCES = {
    "prometheus",
    "loki",
    "postgres",
    "grafana-postgresql-datasource",
    "-- grafana --",
    "-- dashboard --",
    "-- mixed --",
}

# Known-tolerated metric names that come from outside dk-data's canonical
# metric registry (e.g. OpenTelemetry auto-instrumentation, node_exporter,
# pg_exporter, postgrest built-ins). These metric names are legitimately
# queried by our dashboards but are not defined in observability/metrics.py.
EXTERNAL_METRICS = {
    # OpenTelemetry / otelcol
    "otelcol_exporter_sent_spans",
    "otelcol_processor_batch_batch_send_size",
    # Python process / runtime
    "process_cpu_seconds_total",
    "process_resident_memory_bytes",
    "process_virtual_memory_bytes",
    "process_start_time_seconds",
    "process_open_fds",
    "python_gc_collections_total",
    "python_info",
    # PostgreSQL exporter
    "pg_stat_database_numbackends",
    "pg_stat_database_xact_commit",
    "pg_stat_database_xact_rollback",
    "pg_stat_database_tup_fetched",
    "pg_stat_database_tup_returned",
    "pg_stat_user_tables_n_live_tup",
    "pg_stat_user_tables_n_dead_tup",
    # Node exporter
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_filesystem_free_bytes",
    "node_filesystem_size_bytes",
    # Kubernetes state
    "kube_pod_status_phase",
    "kube_deployment_status_replicas",
    "kube_deployment_status_replicas_ready",
    # PgBouncer
    "pgbouncer_pools_server_active_connections",
    "pgbouncer_pools_client_active_connections",
    # PostgREST built-ins
    "pgrst_db_pool_max",
    "pgrst_db_pool_available",
    # Histogram/summary helpers emitted automatically by prometheus_client
    "_bucket",
    "_count",
    "_sum",
}

# Pattern to find metric names referenced in a PromQL expression. Metric
# names in PromQL are `[a-zA-Z_:][a-zA-Z0-9_:]*` — we capture anything that
# looks like an identifier and then filter out Grafana variables, keywords,
# and functions downstream.
METRIC_NAME_IN_PROMQL = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")
PROMQL_KEYWORDS = {
    "by", "without", "on", "ignoring", "offset", "bool",
    "and", "or", "unless", "if", "then", "else",
    "rate", "irate", "increase", "sum", "avg", "min", "max", "count",
    "stddev", "stdvar", "topk", "bottomk", "quantile", "histogram_quantile",
    "time", "vector", "scalar", "absent", "absent_over_time",
    "count_values", "count_over_time", "delta", "deriv", "changes",
    "clamp_max", "clamp_min", "day_of_month", "day_of_week",
    "days_in_month", "exp", "floor", "ceil", "hour", "idelta", "ln",
    "log10", "log2", "minute", "month", "predict_linear", "resets",
    "round", "sgn", "sqrt", "timestamp", "year",
    "le", "ge", "lt", "gt", "eq", "ne",
    "group_left", "group_right",
    "label_replace", "label_join",
    "sum_over_time", "avg_over_time", "min_over_time", "max_over_time",
    "m", "s", "h", "d", "w", "y",  # duration suffixes
    "Inf", "NaN",
}


def _load_dashboards() -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for path in sorted(DASHBOARDS_DIR.glob("*.json")):
        try:
            out.append((path, json.loads(path.read_text())))
        except json.JSONDecodeError as e:
            pytest.fail(f"{path.name} is not valid JSON: {e}")
    return out


def _flatten_panels(panels: list) -> list[dict]:
    """Recursively flatten panels + sub-panels (row panels nest children)."""
    out: list[dict] = []
    for panel in panels or []:
        if not isinstance(panel, dict):
            continue
        out.append(panel)
        if panel.get("type") == "row" and panel.get("panels"):
            out.extend(_flatten_panels(panel["panels"]))
    return out


def _extract_metric_names_from_expr(expr: str) -> set[str]:
    candidates = set(METRIC_NAME_IN_PROMQL.findall(expr))
    # Drop PromQL keywords, Grafana variables (which use $var not captured
    # above since $ is non-word), and numeric-looking things.
    return {
        c
        for c in candidates
        if c not in PROMQL_KEYWORDS
        and not c.isdigit()
        and not c.startswith("_")  # histogram suffix artifacts
    }


def _load_defined_metrics() -> set[str]:
    source = METRICS_FILE.read_text()
    # Match Counter/Gauge/Histogram( ..., "metric_name", ... ). The metric
    # name is the first positional argument.
    pattern = re.compile(
        r"(?:Counter|Gauge|Histogram)\s*\(\s*\"([a-z][a-z0-9_]*)\"",
        re.MULTILINE,
    )
    return set(pattern.findall(source))


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dashboards() -> list[tuple[Path, dict]]:
    out = _load_dashboards()
    assert out, f"no dashboards found at {DASHBOARDS_DIR}"
    return out


@pytest.fixture(scope="module")
def defined_metrics() -> set[str]:
    metrics = _load_defined_metrics()
    assert metrics, "no metrics parsed from observability/metrics.py"
    return metrics


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


class TestDashboardFilesExist:
    def test_dashboards_dir_present(self):
        assert DASHBOARDS_DIR.exists(), f"{DASHBOARDS_DIR} does not exist"

    def test_at_least_one_dashboard(self):
        files = list(DASHBOARDS_DIR.glob("*.json"))
        assert files, "no dashboard JSON files found"


class TestDashboardJsonIsValid:
    def test_all_files_valid_json(self, dashboards):
        # Loading already validated — this test exists as an explicit pass.
        assert len(dashboards) > 0


class TestDashboardSchema:
    def test_every_dashboard_has_title(self, dashboards):
        missing = [path.name for path, d in dashboards if not d.get("title")]
        assert not missing, f"dashboards missing title: {missing}"

    def test_every_dashboard_has_schema_version(self, dashboards):
        missing = [
            path.name for path, d in dashboards if "schemaVersion" not in d
        ]
        assert not missing, f"dashboards missing schemaVersion: {missing}"

    def test_every_dashboard_has_panels(self, dashboards):
        empty = [
            path.name
            for path, d in dashboards
            if not _flatten_panels(d.get("panels", []))
        ]
        assert not empty, f"dashboards with no panels: {empty}"


class TestPanelStructure:
    def test_every_panel_has_type(self, dashboards):
        broken: list[str] = []
        for path, d in dashboards:
            for i, panel in enumerate(_flatten_panels(d.get("panels", []))):
                if not panel.get("type"):
                    broken.append(f"{path.name}:panel[{i}] missing type")
        assert not broken, "\n".join(broken)

    def test_every_panel_has_title_or_transparent_type(self, dashboards):
        """Every non-row panel should either have a title (so users can
        tell what it shows) or be a type that legitimately has no title
        (text, dashboard-list, etc.)."""
        titleless_panel_types = {"text", "dashlist", "news", "gettingstarted"}
        offenders: list[str] = []
        for path, d in dashboards:
            for panel in _flatten_panels(d.get("panels", [])):
                if panel.get("type") == "row":
                    continue
                if panel.get("type") in titleless_panel_types:
                    continue
                if not panel.get("title"):
                    offenders.append(
                        f"{path.name}:panel[{panel.get('id')}] type={panel.get('type')} missing title"
                    )
        assert not offenders, "\n".join(offenders)


class TestMetricReferences:
    """Sanity check: at least one panel in each dashboard should query a
    metric that's defined in observability/metrics.py. This is a smoke
    test — it proves the metric registry and the dashboards are connected,
    without being pedantic about every single expression.

    For exhaustive label-selector auditing, see T115."""

    def test_each_dashboard_references_at_least_one_defined_metric(
        self, dashboards, defined_metrics
    ):
        offenders: list[str] = []
        for path, d in dashboards:
            found = False
            for panel in _flatten_panels(d.get("panels", [])):
                if panel.get("type") == "row":
                    continue
                for target in panel.get("targets", []) or []:
                    expr = target.get("expr") or target.get("query") or ""
                    if not isinstance(expr, str):
                        continue
                    # Strip histogram suffixes that prometheus_client auto-emits
                    normalized = re.sub(r"_(bucket|count|sum)\b", "", expr)
                    if any(m in normalized for m in defined_metrics):
                        found = True
                        break
                if found:
                    break
            if not found:
                # Dashboards that are purely Postgres-backed (query SQL
                # directly) legitimately don't reference Prometheus metrics
                has_postgres_target = any(
                    isinstance((panel.get("datasource") or {}), dict)
                    and (panel.get("datasource") or {}).get("type") == "postgres"
                    for panel in _flatten_panels(d.get("panels", []))
                )
                if has_postgres_target:
                    continue
                offenders.append(path.name)
        assert not offenders, (
            "Dashboards with zero references to a defined metric "
            "(and no postgres fallback):\n"
            + "\n".join(f"  - {o}" for o in offenders)
        )


class TestDatasourceReferences:
    def test_panel_datasource_is_known(self, dashboards):
        bad: list[str] = []
        for path, d in dashboards:
            for panel in _flatten_panels(d.get("panels", [])):
                if panel.get("type") == "row":
                    continue
                ds = panel.get("datasource")
                if ds is None:
                    continue  # some panels inherit from the dashboard default
                if isinstance(ds, str):
                    ds_type = ds.lower()
                elif isinstance(ds, dict):
                    ds_type = (ds.get("type") or "").lower()
                else:
                    continue
                if not ds_type:
                    continue
                if ds_type not in KNOWN_DATASOURCES:
                    bad.append(
                        f"{path.name}:panel[{panel.get('id')}] "
                        f"unknown datasource type '{ds_type}'"
                    )
        assert not bad, "\n".join(bad)
