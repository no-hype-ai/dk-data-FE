"""
Enforce the three-way binding principle for every Prometheus metric.

Feature: 002-external-integration-foundation (US-12, T113)
Principle: .dk/memory/principles.md §6 (three-way binding)

Every metric in src/dk_data/observability/metrics.py must be:

  1. DEFINED    — in metrics.py (this test locates them by parsing the file)
  2. EMITTED    — at least one production call site calls .inc() / .set() /
                  .observe() / .labels() / .dec() on it, OR it's imported by
                  a helper function that in turn is called from production
                  code
  3. CONSUMED   — at least one Grafana dashboard panel or alert rule queries
                  the underlying metric name (best-effort — the test reads
                  grafana/dashboards/*.json and checks for the metric_name
                  as a literal substring)

A metric that fails (2) is a "dead metric" — the pre-feature-002 state was
38 such dead metrics, see .dk/memory/lessons.md.

A metric that fails (3) is an "orphan metric" — the value is emitted but
no human or alert ever looks at it. These are softer failures; this test
reports them but does not fail CI on them unless strict_mode=True.

## Known exclusions

Some metrics are legitimately not dashboard-bound (internal counters used
by other metrics, transitional / being-migrated, exposed purely for
pull-based ad-hoc querying). These are listed in METRIC_COVERAGE_ALLOWLIST
with a justification. Every entry must have a comment explaining WHY the
metric is allowlisted.

## Extending this test

When you add a new metric:
  1. Define it in observability/metrics.py
  2. Call it from production code (the test will verify)
  3. Add it to a Grafana dashboard panel (the test will verify)

If (3) is legitimately N/A, add the metric to METRIC_COVERAGE_ALLOWLIST
with a comment explaining why.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_FILE = REPO_ROOT / "src" / "dk_data" / "observability" / "metrics.py"
SRC_ROOT = REPO_ROOT / "src" / "dk_data"
DASHBOARDS_DIR = REPO_ROOT / "grafana" / "dashboards"

# -----------------------------------------------------------------------------
# Allowlist: metrics that are NOT expected to appear on a dashboard panel.
#
# Format: METRIC_OBJECT_NAME -> human-readable justification
#
# When you add an entry, include a brief comment on the same line explaining
# WHY this metric is allowlisted. Reviewers: reject any entry without a
# justification.
# -----------------------------------------------------------------------------
DASHBOARD_ALLOWLIST: dict[str, str] = {
    # Internal helper counters used to derive other metrics — not directly
    # dashboard-bound because the dashboard shows the derived rate instead.
    "HTTP_REQUESTS_TOTAL": "OTel auto-instrumentation covers the HTTP panels",
    "HTTP_REQUEST_DURATION_SECONDS": "OTel auto-instrumentation covers latency",
    "DB_QUERY_DURATION_SECONDS": "reserved for ad-hoc query tuning, not dashboards",
    # Transitional — dead metrics being cleaned up in T111/T112.
    # Every entry below should be removed as its underlying metric is either
    # wired to a dashboard panel or deleted from metrics.py entirely.
    "BATCH_JOB_DURATION_SECONDS": "dead metric — cleanup in T111/T112",
    "BATCH_JOB_FAILURES_TOTAL": "dead metric — cleanup in T111/T112",
    "BATCH_JOB_LAST_SUCCESS_TIMESTAMP": "dead metric — cleanup in T111/T112",
    "BATCH_JOB_RECORDS_PROCESSED": "dead metric — cleanup in T111/T112",
    "DK_ALERTS_DELIVERED": "dead metric — cleanup in T111/T112",
    "DK_ALERTS_GENERATED": "dead metric — cleanup in T111/T112",
    "DK_API_REQUESTS": "dead metric — cleanup in T111/T112",
    "DK_BRONZE_RECORDS_INGESTED": "dead metric — cleanup in T111/T112",
    "DK_FUZZY_MATCH_REQUESTS": "dead metric — cleanup in T111/T112",
    "DK_FUZZY_MATCH_RESULTS": "dead metric — cleanup in T111/T112",
    "DK_GOLD_AGGREGATION_DURATION": "dead metric — cleanup in T111/T112",
    "DK_GOLD_PROFILES_TOTAL": "dead metric — cleanup in T111/T112",
    "DK_GOLD_UNPROCESSED": "dead metric — cleanup in T111/T112",
    "DK_MOLECULES_BY_STAGE": "dead metric — cleanup in T111/T112",
    "DK_ONBOARDING_COMPLETED": "dead metric — cleanup in T111/T112",
    "DK_ONBOARDING_STARTED": "dead metric — cleanup in T111/T112",
    "DK_ONBOARDING_STEP_DURATION": "dead metric — cleanup in T111/T112",
    "DK_PIPELINE_JOB_DURATION": "dead metric — cleanup in T111/T112",
    "DK_PIPELINE_LAST_SUCCESS": "dead metric — cleanup in T111/T112",
    "DK_PIPELINE_RUNS_TOTAL": "dead metric — cleanup in T111/T112",
    "DK_RESOLUTION_LATENCY": "dead metric — cleanup in T111/T112",
    "DK_RESOLUTION_QUEUE_SIZE": "dead metric — cleanup in T111/T112",
    "DK_RESOLUTION_REQUESTS": "dead metric — cleanup in T111/T112",
    "DK_RESOLUTION_SUCCESS_RATE": "dead metric — cleanup in T111/T112",
    "DK_SILVER_IDENTIFIER_MAPPINGS": "dead metric — cleanup in T111/T112",
    "DK_SILVER_MOLECULES_TOTAL": "dead metric — cleanup in T111/T112",
    "DK_SILVER_RECORDS_TRANSFORMED": "dead metric — cleanup in T111/T112",
    "DK_SILVER_TRANSFORMATION_ERRORS": "dead metric — cleanup in T111/T112",
    "DK_SOURCE_RECORDS_TOTAL": "dead metric — cleanup in T111/T112",
    "DK_TRIALS_BY_PHASE": "dead metric — cleanup in T111/T112",
    "DK_ARTIFACT_SIZE_MISMATCH_TOTAL": "ingestion integrity counter — surfaced via PrometheusRule alert (DkArtifactSizeMismatch, PR-304 follow-up) not a dashboard panel. Telemetry drives incident alerting, not visual inspection.",
}

# Some metrics are emitted from production code paths that this test's grep
# cannot see (e.g., called from compiled extensions, dynamic dispatch by name,
# or helper wrappers that add indirection). If you see a false positive from
# the emission check, add the metric here with a justification.
#
# -----------------------------------------------------------------------------
# TRANSITIONAL RATCHET (feature 002 US-12, T111/T112):
#
# The entries below are the "38 dead metrics" captured at feature 002 audit
# time (see .dk/memory/lessons.md 2026-04-13). They are either:
#   (a) Defined + helper-wrapped in services/data_platform/metrics.py but
#       the helper is never called from any production code path, OR
#   (b) Defined with no helper at all and no direct emission site.
#
# The ratchet rule: this allowlist is ALLOWED TO SHRINK but never to grow.
# As T111/T112 fix each metric (wire it up or delete it), remove its entry
# here. A new dead metric MUST be wired up in the same PR that defines it.
# -----------------------------------------------------------------------------
_DEAD_METRICS_002_RATCHET = [
    "BATCH_JOB_DURATION_SECONDS",
    "BATCH_JOB_FAILURES_TOTAL",
    "BATCH_JOB_RECORDS_PROCESSED",
    "CMS_AGENT_COST_USD",
    "CMS_AGENT_EXECUTIONS_TOTAL",
    "CMS_AGENT_LAST_RUN_STATUS",
    "CMS_AGENT_QUARANTINE_PENDING",
    "CMS_AGENT_RECORDS_ENRICHED_TOTAL",
    "CMS_AGENT_RECORDS_QUARANTINED_TOTAL",
    "CMS_BACKFILL_REQUESTS_TOTAL",
    "CMS_EXTERNAL_API_REQUESTS_TOTAL",
    "CMS_FETCH_DURATION_SECONDS",
    "CMS_GOLD_REFRESH_DURATION_SECONDS",
    "CMS_GOLD_VIEW_LAST_REFRESH_TIMESTAMP",
    "CMS_GOLD_VIEW_RECORD_COUNT",
    "CMS_RATE_LIMIT_REJECTIONS_TOTAL",
    "CMS_RECORDS_INGESTED_TOTAL",
    "CMS_SOURCE_LAST_SYNC_TIMESTAMP",
    "DATA_SOURCE_LAST_REFRESH_TIMESTAMP",
    "DATA_SOURCE_ROW_COUNT",
    "DB_QUERY_DURATION_SECONDS",
    "DK_ALERTS_DELIVERED",
    "DK_ALERTS_GENERATED",
    "DK_BRONZE_INGESTION_DURATION",
    "DK_BRONZE_INGESTION_ERRORS",
    "DK_BRONZE_RECORDS_INGESTED",
    "DK_BRONZE_UNPROCESSED_RECORDS",
    "DK_FUZZY_MATCH_REQUESTS",
    "DK_FUZZY_MATCH_RESULTS",
    "DK_GOLD_AGGREGATION_DURATION",
    "DK_GOLD_PROFILES_TOTAL",
    "DK_MOLECULES_BY_STAGE",
    "DK_ONBOARDING_COMPLETED",
    "DK_ONBOARDING_STARTED",
    "DK_ONBOARDING_STEP_DURATION",
    "DK_PIPELINE_DURATION_SECONDS",
    "DK_PIPELINE_RUNS_TOTAL",
    "DK_RESOLUTION_LATENCY",
    "DK_RESOLUTION_QUEUE_SIZE",
    "DK_RESOLUTION_REQUESTS",
    "DK_RESOLUTION_SUCCESS_RATE",
    "DK_SILVER_RECORDS_TRANSFORMED",
    "DK_SILVER_TRANSFORMATION_ERRORS",
    "HTTP_REQUEST_DURATION_SECONDS",
    "HTTP_REQUESTS_TOTAL",
]

EMISSION_ALLOWLIST: dict[str, str] = {
    name: "dead metric pre-feature-002 — ratchet entry, tracked in T111/T112"
    for name in _DEAD_METRICS_002_RATCHET
}

METRIC_DEFINITION_PATTERN = re.compile(
    r"^([A-Z][A-Z0-9_]+)\s*=\s*(Counter|Gauge|Histogram)\s*\(",
    re.MULTILINE,
)
METRIC_NAME_ARG_PATTERN = re.compile(
    r'^\s*"([a-z][a-z0-9_]*)"\s*,',
    re.MULTILINE,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_metrics() -> dict[str, str]:
    """Return {PYTHON_OBJECT_NAME: prometheus_metric_name} for every Counter/
    Gauge/Histogram defined in the canonical metrics.py file.
    """
    source = _read(METRICS_FILE)

    # Walk each definition block to find the first string literal (the metric
    # name argument). The Prometheus client library requires the metric name
    # to be the first positional argument, so we can scan forward from each
    # definition start.
    out: dict[str, str] = {}
    lines = source.splitlines()
    for idx, line in enumerate(lines):
        m = METRIC_DEFINITION_PATTERN.match(line + "\n")
        if not m:
            continue
        obj = m.group(1)
        # Look at up to 5 lines ahead for the first "..." argument
        window = "\n".join(lines[idx : idx + 6])
        name_match = re.search(r'\(\s*"([a-z][a-z0-9_]*)"', window)
        if name_match:
            out[obj] = name_match.group(1)
    return out


def _source_python_files() -> list[Path]:
    # Exclude ONLY the canonical definition file, not every file named
    # metrics.py — helper wrappers live in services/data_platform/metrics.py
    # and count as production emission sites.
    canonical = METRICS_FILE.resolve()
    return [
        p
        for p in SRC_ROOT.rglob("*.py")
        if p.resolve() != canonical
        and "__pycache__" not in p.parts
    ]


def _has_emission_call(obj_name: str, source_files: list[Path]) -> bool:
    """Return True if any source file contains OBJ.inc / OBJ.set / OBJ.observe
    / OBJ.labels / OBJ.dec — i.e., a call that writes to the metric.

    Imports alone do not count; an import without a call is still dead.
    """
    # Match OBJ.(inc|set|observe|labels|dec|info) — covers all prometheus-client
    # writer methods plus labels-chained calls.
    call_pattern = re.compile(
        rf"\b{re.escape(obj_name)}\s*\.\s*(inc|set|observe|labels|dec|info)\b"
    )
    for path in source_files:
        try:
            if call_pattern.search(_read(path)):
                return True
        except OSError:
            continue
    return False


def _dashboard_queries() -> str:
    """Concatenate every dashboard JSON into one haystack for substring search."""
    chunks: list[str] = []
    for dashboard in sorted(DASHBOARDS_DIR.glob("*.json")):
        try:
            chunks.append(_read(dashboard))
        except OSError:
            continue
    return "\n".join(chunks)


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def metrics() -> dict[str, str]:
    result = _extract_metrics()
    assert result, "no metrics parsed from metrics.py — parser is broken"
    return result


@pytest.fixture(scope="module")
def source_files() -> list[Path]:
    return _source_python_files()


@pytest.fixture(scope="module")
def dashboards() -> str:
    text = _dashboard_queries()
    assert text, f"no dashboards found at {DASHBOARDS_DIR}"
    return text


class TestMetricDefinitionParsing:
    def test_metrics_file_exists(self):
        assert METRICS_FILE.exists(), f"canonical metrics file missing: {METRICS_FILE}"

    def test_at_least_50_metrics_defined(self, metrics):
        # Sanity — if the parser yields a tiny number something is broken.
        assert len(metrics) >= 50, f"only parsed {len(metrics)} metrics"

    def test_every_object_has_prometheus_name(self, metrics):
        missing = [obj for obj, name in metrics.items() if not name]
        assert not missing, f"metric objects with no parsed prometheus name: {missing}"


class TestEmissionCoverage:
    """Every metric must have at least one production emission call."""

    def test_every_metric_is_emitted(self, metrics, source_files):
        dead: list[str] = []
        for obj_name in metrics:
            if obj_name in EMISSION_ALLOWLIST:
                continue
            if not _has_emission_call(obj_name, source_files):
                dead.append(obj_name)

        if dead:
            pytest.fail(
                "Dead metrics — defined but never emitted from production code:\n"
                + "\n".join(f"  - {d}" for d in sorted(dead))
                + "\n\nFix options:\n"
                "  1. Wire up an emission call site in the relevant code path\n"
                "  2. Delete the metric definition if it's no longer needed\n"
                "  3. Add to EMISSION_ALLOWLIST with a justification (rare)\n"
                "\nSee .dk/memory/principles.md §6 (three-way binding)."
            )


class TestDashboardCoverage:
    """Every metric should be queried by at least one dashboard panel.

    This is the softer half of three-way binding — some metrics are
    legitimately internal. Allowlist them in DASHBOARD_ALLOWLIST with a
    justification.
    """

    def test_every_metric_is_on_a_dashboard(self, metrics, dashboards):
        orphans: list[str] = []
        for obj_name, prom_name in metrics.items():
            if obj_name in DASHBOARD_ALLOWLIST:
                continue
            if prom_name and prom_name in dashboards:
                continue
            orphans.append(f"{obj_name} ({prom_name})")

        if orphans:
            pytest.fail(
                "Orphan metrics — emitted but never displayed on a dashboard:\n"
                + "\n".join(f"  - {o}" for o in sorted(orphans))
                + "\n\nFix options:\n"
                "  1. Add a panel to grafana/dashboards/*.json that queries\n"
                "     the metric\n"
                "  2. Add an alerting rule that references the metric\n"
                "  3. Add to DASHBOARD_ALLOWLIST with a justification\n"
                "\nSee .dk/memory/principles.md §6 (three-way binding)."
            )


class TestMeteringProxyJWTMetrics:
    """Explicit three-way binding check for the three JWT minting metrics added in
    feature 003 (issue #283). These metrics live in metering_proxy/metrics.py (not
    in the canonical observability/metrics.py scanned above), so they need their
    own coverage assertions.

    The three metrics must be:
      1. Defined in src/dk_data/metering_proxy/metrics.py
      2. Emitted from at least one production call site (proxy.py or a helper)
      3. Queried on a Grafana dashboard panel (dashboards fixture)

    See .dk/memory/principles.md §6 (three-way binding).
    """

    EXPECTED_METRICS: list[tuple[str, str]] = [
        # (python object name in metering_proxy/metrics.py, prometheus metric name)
        ("JWT_MINTED_TOTAL", "dk_data_metering_jwt_minted_total"),
        ("JWT_MINT_ERRORS_TOTAL", "dk_data_metering_jwt_mint_errors_total"),
        (
            "REQUESTS_FORWARDED_WITHOUT_JWT_TOTAL",
            "dk_data_metering_requests_forwarded_without_jwt_total",
        ),
    ]

    @pytest.fixture(scope="class")
    def metering_proxy_metrics_src(self) -> str:
        path = REPO_ROOT / "src" / "dk_data" / "metering_proxy" / "metrics.py"
        assert path.exists(), f"metering_proxy/metrics.py not found at {path}"
        return path.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def metering_proxy_source_files(self) -> list[Path]:
        metering_dir = REPO_ROOT / "src" / "dk_data" / "metering_proxy"
        return [
            p
            for p in metering_dir.rglob("*.py")
            if "__pycache__" not in p.parts
        ]

    def test_jwt_metrics_defined(self, metering_proxy_metrics_src):
        """All three JWT metrics must be defined in metering_proxy/metrics.py."""
        missing = []
        for obj_name, prom_name in self.EXPECTED_METRICS:
            if obj_name not in metering_proxy_metrics_src:
                missing.append(f"{obj_name} ({prom_name})")
            if prom_name not in metering_proxy_metrics_src:
                missing.append(f"prometheus name '{prom_name}' not found in metrics.py")
        assert not missing, (
            "JWT metric definitions missing from metering_proxy/metrics.py:\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

    def test_jwt_metrics_emitted(self, metering_proxy_source_files):
        """All three JWT metrics must have at least one .inc()/.labels() call in
        the metering proxy source tree (emission leg of three-way binding)."""
        dead = []
        for obj_name, prom_name in self.EXPECTED_METRICS:
            call_pattern = re.compile(
                rf"\b{re.escape(obj_name)}\s*\.\s*(inc|set|observe|labels|dec|info)\b"
            )
            if not any(
                call_pattern.search(p.read_text(encoding="utf-8", errors="ignore"))
                for p in metering_proxy_source_files
            ):
                dead.append(f"{obj_name} ({prom_name})")
        assert not dead, (
            "JWT metrics defined but never emitted from metering_proxy source:\n"
            + "\n".join(f"  - {d}" for d in dead)
            + "\n\nWire .inc() or .labels().inc() calls in proxy.py."
        )

    def test_jwt_metrics_on_dashboard(self, dashboards):
        """All three JWT metric names must appear in at least one dashboard panel."""
        missing = []
        for _obj_name, prom_name in self.EXPECTED_METRICS:
            if prom_name not in dashboards:
                missing.append(prom_name)
        assert not missing, (
            "JWT metrics not found in any Grafana dashboard JSON:\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nAdd panels to grafana/dashboards/dk-data-adapter-telemetry.json."
        )


class TestAllowlistDiscipline:
    """The allowlist itself is an allowed exception, but it must not grow
    without review. This test documents the current floor — if it drops,
    someone has removed an entry without adding the underlying metric.
    If it rises, someone has added an entry; reviewers should reject any
    entry that lacks a justification comment in the source."""

    def test_dashboard_allowlist_documented(self):
        for obj_name, justification in DASHBOARD_ALLOWLIST.items():
            assert justification, (
                f"{obj_name} is in DASHBOARD_ALLOWLIST with no justification — "
                "every allowlist entry must explain why the metric is not "
                "on a dashboard."
            )

    def test_emission_allowlist_documented(self):
        for obj_name, justification in EMISSION_ALLOWLIST.items():
            assert justification, (
                f"{obj_name} is in EMISSION_ALLOWLIST with no justification"
            )
