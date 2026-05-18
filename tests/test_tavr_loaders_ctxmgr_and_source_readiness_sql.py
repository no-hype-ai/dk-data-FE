"""Network-free regression tests for the #416 follow-up fix.

Found by kicking the prod TAVR fetchers after PR #416 (commit 118a2c0):

PART A — `get_connection()` is a `@contextmanager`, but four more TAVR
loaders still called it as a plain function and then `conn.close()`,
which raises `'_GeneratorContextManager' object has no attribute
'close'` at runtime (confirmed in prod for tavr_program_year). #416 had
already fixed this in tavr_source_readiness.py / tavr_catalog_data_gov.py.
These tests patch `get_connection` with a real context manager yielding a
fake connection and assert each loader runs to its success envelope
WITHOUT the AttributeError the pre-fix code raised.

PART B — `tavr_source_readiness._HEALTH_LOOKUP_SQL` was written against a
non-existent schema (`meta.refresh_log.source_name`,
`meta.refresh_log.last_successful_refresh`, `meta.refresh_log.row_count`,
`meta.table_health.source_name` — none exist; prod failed with
`column th.source_name does not exist`). The corrected SQL reads
`meta.data_sources` (keyed by `source_name`, freshness from
`last_successful_refresh`, rowcount from `record_count`) joined to the
latest `meta.table_health` row by `source_id`/`check_timestamp`, while
preserving the existing 4-column SELECT order so the unpack + the
unchanged `_classify_source` keep working.

No external network or DB calls are made — the connection context
manager is patched (mirrors tests/test_cms_geographic_variation_loader.py).

Follow-up to #416. Unblocks edwards-meadow EM-3/EM-4/EM-5/EM-6.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from dk_data.ingestion.sources.tavr_source_readiness import (
    _HEALTH_LOOKUP_SQL,
    _classify_source,
    load_tavr_source_readiness_data,
)


def _fake_get_connection(cursor: MagicMock):
    """Build a `get_connection` replacement that is a context manager
    yielding a fake connection whose `.cursor()` is itself a context
    manager yielding `cursor`. This matches the real
    `@contextmanager def get_connection()` contract, so a loader that
    (incorrectly) did `conn = get_connection(); ...; conn.close()` would
    still raise AttributeError here — exactly the prod bug — while the
    fixed `with get_connection() as conn:` form works.
    """

    @contextmanager
    def _cursor_ctx():
        yield cursor

    fake_conn = MagicMock()
    fake_conn.cursor.side_effect = lambda *a, **k: _cursor_ctx()

    @contextmanager
    def _conn_ctx(*args, **kwargs):
        yield fake_conn

    return _conn_ctx, fake_conn


# ---------------------------------------------------------------------------
# PART A — the four loaders #416 did not cover.
# Each loader runs one build SQL then a COUNT(*) returning a scalar tuple.
# Pre-fix code raised AttributeError on conn.close(); post-fix it must
# return the standard success envelope.
# ---------------------------------------------------------------------------

_PART_A_LOADERS = [
    (
        "dk_data.ingestion.sources.tavr_program_year",
        "load_tavr_program_year_data",
    ),
    (
        "dk_data.ingestion.sources.tavr_benchmark_inputs",
        "load_tavr_benchmark_inputs_data",
    ),
    (
        "dk_data.ingestion.sources.tavr_public_proxy_profile",
        "load_tavr_public_proxy_profile_data",
    ),
    (
        "dk_data.ingestion.sources.tavr_hospital_profile",
        "load_tavr_hospital_profile_data",
    ),
]


@pytest.mark.parametrize("module_path,func_name", _PART_A_LOADERS)
def test_part_a_loader_uses_get_connection_as_context_manager(
    module_path, func_name
):
    import importlib

    mod = importlib.import_module(module_path)
    loader = getattr(mod, func_name)

    cursor = MagicMock()
    cursor.rowcount = 7
    cursor.fetchone.return_value = (42,)  # _COUNT_ROWS_SQL scalar

    conn_ctx, fake_conn = _fake_get_connection(cursor)

    with patch.object(mod, "get_connection", conn_ctx):
        # Pre-fix this raised:
        #   AttributeError: '_GeneratorContextManager' object has no
        #   attribute 'close'
        result = loader([])

    assert result["status"] == "success"
    assert result["records_inserted"] == 7
    assert result["record_count"] == 7
    assert result["total_rows"] == 42
    fake_conn.commit.assert_called_once()
    fake_conn.rollback.assert_not_called()
    # The ctx manager's finally returns the conn via pool.putconn; the
    # loader must NOT call conn.close() itself anymore.
    fake_conn.close.assert_not_called()


@pytest.mark.parametrize("module_path,func_name", _PART_A_LOADERS)
def test_part_a_loader_rolls_back_and_reraises_on_error(
    module_path, func_name
):
    import importlib

    mod = importlib.import_module(module_path)
    loader = getattr(mod, func_name)

    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError("boom")

    conn_ctx, fake_conn = _fake_get_connection(cursor)

    with patch.object(mod, "get_connection", conn_ctx):
        with pytest.raises(RuntimeError, match="boom"):
            loader([])

    fake_conn.rollback.assert_called_once()
    fake_conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# PART B — _HEALTH_LOOKUP_SQL targets the real meta schema and the
# existing 4-column unpack + _classify_source are untouched.
# ---------------------------------------------------------------------------

def test_part_b_health_lookup_sql_targets_real_schema():
    sql = _HEALTH_LOOKUP_SQL

    # Reads the table that actually has freshness + rowcount keyed by name.
    assert "meta.data_sources" in sql
    assert "ds.source_name = %s" in sql
    assert "ds.last_successful_refresh" in sql
    assert "ds.record_count" in sql

    # Latest health row joined by the real FK + ordering column.
    assert "meta.table_health" in sql
    assert "th.source_id = ds.source_id" in sql
    assert "th.check_timestamp" in sql

    # The non-existent columns that broke prod must be gone.
    assert "rl.source_name" not in sql
    assert "rl.last_successful_refresh" not in sql
    assert "rl.row_count" not in sql
    assert "th.source_name" not in sql

    # Exactly one bind param (= source_name); 4-column SELECT contract.
    assert sql.count("%s") == 1


def test_part_b_four_column_unpack_still_feeds_classify_source():
    """Drive the loader through a fake cursor: _COLLECT_SOURCES_SQL
    returns one source, _HEALTH_LOOKUP_SQL returns a 4-tuple in the
    documented order, and the loader must unpack + classify + upsert
    without touching _classify_source.
    """
    import dk_data.ingestion.sources.tavr_source_readiness as mod

    # last_refresh, row_count, health_status, age_hours  (the contract)
    health_row = ("2026-05-01 00:00:00", 1234, "healthy", 10.0)

    cursor = MagicMock()

    def _execute(sql, params=None):
        cursor._last_sql = sql

    def _fetchall():
        return [("cms_inpatient_puf",)]  # _COLLECT_SOURCES_SQL

    def _fetchone():
        return health_row  # _HEALTH_LOOKUP_SQL

    cursor.execute.side_effect = _execute
    cursor.fetchall.side_effect = _fetchall
    cursor.fetchone.side_effect = _fetchone

    conn_ctx, fake_conn = _fake_get_connection(cursor)

    with patch.object(mod, "get_connection", conn_ctx):
        result = load_tavr_source_readiness_data([])

    assert result["status"] == "success"
    assert result["record_count"] >= 1
    # 4-tuple in that order + this source_class must classify claim_eligible
    # (fresh, healthy, public_machine_readable) — proves the unpack order
    # and untouched _classify_source still line up.
    assert _classify_source("2026-05-01", 10.0, "healthy",
                            "public_machine_readable") == "claim_eligible"
    assert result["claim_eligible"] >= 1
    fake_conn.commit.assert_called_once()
