"""Tests for log_to_meta() function.

Covers:
- Unit tests with mocked DB (fast, no real Postgres required)
- Structural checks (loaders must not call log_to_meta)
- SOURCES dict coverage
- Integration tests against real PostgreSQL schema (marked with @pytest.mark.integration)
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests: log_to_meta() logic with mocked DB cursor
# ---------------------------------------------------------------------------

class TestLogToMetaUnit:
    """Unit tests for log_to_meta() without a real database."""

    def _make_cursor(self, source_id=42):
        """Return a mock cursor that returns a source_id on first fetchone."""
        cursor = MagicMock()
        cursor.fetchone.return_value = (source_id,)
        return cursor

    def _call_log_to_meta(self, source_name, result, cursor):
        from dk_data.ingestion.main import log_to_meta
        with patch("dk_data.ingestion.main.get_cursor") as mock_get_cursor:
            # get_cursor() is used as a context manager
            mock_cm = MagicMock()
            mock_cm.__enter__ = MagicMock(return_value=cursor)
            mock_cm.__exit__ = MagicMock(return_value=False)
            mock_get_cursor.return_value = mock_cm
            log_to_meta(source_name, result)

    def test_success_status_updates_last_successful_refresh(self):
        cursor = self._make_cursor()
        result = {
            "status": "success",
            "records_fetched": 100,
            "records_inserted": 100,
            "records_updated": 0,
            "errors": [],
        }
        self._call_log_to_meta("cms_part_d_spending", result, cursor)

        # Should have called execute 4 times: INSERT upsert, SELECT source_id, INSERT refresh_log, UPDATE data_sources
        assert cursor.execute.call_count == 4

    def test_failed_status_does_not_update_last_successful_refresh(self):
        cursor = self._make_cursor()
        result = {
            "status": "failed",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": ["Connection timeout"],
        }
        self._call_log_to_meta("cms_part_d_spending", result, cursor)
        assert cursor.execute.call_count == 4

    def test_partial_status_updates_last_successful_refresh(self):
        cursor = self._make_cursor()
        result = {
            "status": "partial",
            "records_fetched": 100,
            "records_inserted": 95,
            "records_updated": 5,
            "errors": ["5 rows skipped"],
        }
        self._call_log_to_meta("cms_part_d_spending", result, cursor)
        assert cursor.execute.call_count == 4

    def test_unknown_source_name_is_noop(self):
        cursor = self._make_cursor(source_id=None)
        cursor.fetchone.return_value = None  # source not found after upsert
        result = {"status": "success", "records_inserted": 10, "errors": []}
        self._call_log_to_meta("nonexistent_source", result, cursor)
        # INSERT upsert + SELECT were executed; INSERT log and UPDATE were skipped
        assert cursor.execute.call_count == 2

    def test_errors_truncated_to_5(self):
        cursor = self._make_cursor()
        errors = [f"error {i}" for i in range(10)]
        result = {
            "status": "partial",
            "records_fetched": 10,
            "records_inserted": 5,
            "records_updated": 0,
            "errors": errors,
        }
        self._call_log_to_meta("cms_nppes", result, cursor)
        # Extract the error_message argument from the INSERT call (3rd execute call, index 2)
        insert_call_args = cursor.execute.call_args_list[2]
        error_json_arg = insert_call_args[0][1][-1]  # last positional param
        error_list = json.loads(error_json_arg)
        assert len(error_list) == 5

    def test_no_errors_writes_none(self):
        cursor = self._make_cursor()
        result = {
            "status": "success",
            "records_fetched": 50,
            "records_inserted": 50,
            "records_updated": 0,
            "errors": [],
        }
        self._call_log_to_meta("cms_open_payments", result, cursor)
        insert_call_args = cursor.execute.call_args_list[2]
        error_arg = insert_call_args[0][1][-1]
        assert error_arg is None

    def test_db_exception_is_caught(self):
        """log_to_meta() must not raise even if DB fails."""
        cursor = MagicMock()
        cursor.execute.side_effect = Exception("DB connection lost")
        result = {"status": "success", "records_inserted": 10, "errors": []}
        # Should not raise
        self._call_log_to_meta("cms_part_d_spending", result, cursor)


# ---------------------------------------------------------------------------
# Structural tests: loaders must NOT call log_to_meta()
# ---------------------------------------------------------------------------

class TestLoadersDoNotCallLogToMeta:
    """Verify no CMS PUF loader file calls log_to_meta() directly."""

    CMS_PUF_LOADER_MODULES = [
        "cms_part_d_spending",
        "cms_part_b_spending",
        "cms_open_payments",
        "cms_nppes",
        "cms_inpatient_puf",
        "cms_physician_puf",
        "cms_hospital_general_info",
        "cms_medicare_advantage",
        "cms_medicaid_drug_spending",
        "cms_dme_puf",
        "cms_home_health",
        "cms_hospice_puf",
        "cms_snf_puf",
        "cms_outpatient_puf",
        "cms_referring_providers",
        "cms_ordering_providers",
        "cms_lab_services",
        "cms_imaging_puf",
        "cms_mental_health_puf",
        "cms_opioid_puf",
        "cms_telehealth_puf",
        "cms_geographic_variation",
        "cms_chronic_conditions",
        "cms_dual_eligible",
        "cms_enrollment_puf",
        "cms_claim_type_puf",
        "cms_utilization_puf",
        "cms_cost_reports_puf",
        "europepmc",
        "nih_reporter",
    ]

    def test_no_loader_imports_log_to_meta(self):
        """No CMS PUF loader source file should import or call log_to_meta()."""
        import pathlib

        sources_dir = pathlib.Path(__file__).parent.parent / "src" / "dk_data" / "ingestion" / "sources"
        assert sources_dir.exists(), f"Sources dir not found: {sources_dir}"

        violations = []
        for module_name in self.CMS_PUF_LOADER_MODULES:
            source_file = sources_dir / f"{module_name}.py"
            if not source_file.exists():
                continue  # Skip files not yet written (background agent may be writing them)
            content = source_file.read_text()
            if "log_to_meta" in content:
                violations.append(module_name)

        assert violations == [], (
            f"These loaders illegally reference log_to_meta(): {violations}. "
            "log_to_meta() must only be called by run_ingestion() in main.py."
        )

    def test_run_ingestion_calls_log_to_meta(self):
        """Verify run_ingestion() in main.py calls log_to_meta()."""
        import pathlib
        main_file = pathlib.Path(__file__).parent.parent / "src" / "dk_data" / "ingestion" / "main.py"
        content = main_file.read_text()
        assert "log_to_meta" in content, "run_ingestion() in main.py must call log_to_meta()"
        # Verify it's defined in main.py (not just imported)
        assert "def log_to_meta(" in content, "log_to_meta() must be defined in main.py"


# ---------------------------------------------------------------------------
# SOURCES dict coverage tests
# ---------------------------------------------------------------------------

class TestSourcesDictCoverage:
    """Verify all 30 new sources are registered in SOURCES."""

    EXPECTED_NEW_SOURCES = [
        "cms_part_d_spending", "cms_part_b_spending", "cms_open_payments",
        "cms_nppes", "cms_inpatient_puf", "cms_physician_puf",
        "cms_hospital_general_info", "cms_medicare_advantage",
        "cms_medicaid_drug_spending", "cms_dme_puf", "cms_home_health",
        "cms_hospice_puf", "cms_snf_puf", "cms_outpatient_puf",
        "cms_referring_providers", "cms_ordering_providers", "cms_lab_services",
        "cms_imaging_puf", "cms_mental_health_puf", "cms_opioid_puf",
        "cms_telehealth_puf", "cms_geographic_variation", "cms_chronic_conditions",
        "cms_dual_eligible", "cms_enrollment_puf", "cms_claim_type_puf",
        "cms_utilization_puf", "cms_cost_reports_puf",
        "europepmc", "nih_reporter",
    ]

    def test_all_new_sources_in_sources_dict(self):
        from dk_data.ingestion.main import SOURCES
        missing = [s for s in self.EXPECTED_NEW_SOURCES if s not in SOURCES]
        assert missing == [], f"Missing sources from SOURCES dict: {missing}"

    def test_total_source_count_at_least_52(self):
        from dk_data.ingestion.main import SOURCES
        assert len(SOURCES) >= 52, (
            f"Expected at least 52 sources (22 original + 30 new), got {len(SOURCES)}"
        )

    def test_cms_puf_sources_have_requires_file_or_self_loading(self):
        from dk_data.ingestion.main import SOURCES
        cms_puf_sources = [s for s in self.EXPECTED_NEW_SOURCES if s not in ("europepmc", "nih_reporter")]
        for source in cms_puf_sources:
            info = SOURCES[source]
            assert info.get("requires_file") is True or info.get("self_loading") is True, (
                f"CMS PUF source '{source}' must have requires_file=True or self_loading=True"
            )

    def test_api_sources_have_fetcher(self):
        from dk_data.ingestion.main import SOURCES
        for source in ("europepmc", "nih_reporter"):
            assert "fetcher" in SOURCES[source], (
                f"API source '{source}' must have a fetcher in SOURCES dict"
            )
            assert "loader" in SOURCES[source], (
                f"API source '{source}' must have a loader in SOURCES dict"
            )


# ---------------------------------------------------------------------------
# Integration tests: real PostgreSQL schema (require --integration flag)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLogToMetaIntegration:
    """Integration tests for log_to_meta() against real PostgreSQL schema."""

    TEST_SOURCE = "_test_source_ltm"

    @pytest.fixture(autouse=True)
    def _pool(self, monkeypatch, ingestion_connection_pool):
        yield

    def test_log_to_meta_success(self, postgres_connection, db_cursor):
        """log_to_meta should write refresh_log and update source status."""
        from dk_data.ingestion.main import log_to_meta

        db_cursor.execute(
            """
            INSERT INTO meta.data_sources
                (source_name, source_type, description, is_active, refresh_frequency)
            VALUES (%s, 'api', 'Integration test source', true, 'daily')
            ON CONFLICT (source_name) DO NOTHING
            """,
            (self.TEST_SOURCE,),
        )
        postgres_connection.commit()

        try:
            log_to_meta(
                self.TEST_SOURCE,
                {"status": "success", "records_fetched": 42, "records_inserted": 42},
            )

            db_cursor.execute(
                """
                SELECT rl.status, rl.records_fetched
                FROM meta.refresh_log rl
                JOIN meta.data_sources ds ON ds.source_id = rl.source_id
                WHERE ds.source_name = %s
                ORDER BY rl.log_id DESC
                LIMIT 1
                """,
                (self.TEST_SOURCE,),
            )
            row = db_cursor.fetchone()
            assert row is not None
            assert row[0] == "success"
            assert row[1] == 42

            db_cursor.execute(
                "SELECT last_refresh_status FROM meta.data_sources WHERE source_name = %s",
                (self.TEST_SOURCE,),
            )
            source_row = db_cursor.fetchone()
            assert source_row is not None
            assert source_row[0] == "success"
        finally:
            db_cursor.execute(
                """
                DELETE FROM meta.refresh_log
                WHERE source_id = (
                    SELECT source_id FROM meta.data_sources WHERE source_name = %s
                )
                """,
                (self.TEST_SOURCE,),
            )
            db_cursor.execute("DELETE FROM meta.data_sources WHERE source_name = %s", (self.TEST_SOURCE,))
            postgres_connection.commit()

    def test_log_to_meta_missing_source(self, postgres_connection, db_cursor):
        """log_to_meta auto-registers unknown sources and writes a refresh_log entry.

        The upsert ensures that sources not pre-seeded in meta.data_sources still
        get last_successful_refresh tracked (e.g. nih_reporter, europepmc).
        """
        from dk_data.ingestion.main import log_to_meta

        missing_source = "_test_nonexistent_xyz"
        try:
            log_to_meta(missing_source, {"status": "success", "records_fetched": 0})

            db_cursor.execute(
                "SELECT COUNT(*) FROM meta.refresh_log WHERE source_name = %s",
                (missing_source,),
            )
            count = db_cursor.fetchone()[0]
            assert count == 1  # source was auto-registered and logged

            db_cursor.execute(
                "SELECT source_name FROM meta.data_sources WHERE source_name = %s",
                (missing_source,),
            )
            assert db_cursor.fetchone() is not None  # auto-registered
            postgres_connection.commit()
        finally:
            db_cursor.execute(
                "DELETE FROM meta.refresh_log WHERE source_name = %s", (missing_source,)
            )
            db_cursor.execute(
                "DELETE FROM meta.data_sources WHERE source_name = %s", (missing_source,)
            )
            postgres_connection.commit()

    def test_log_to_meta_refresh_log_schema(self, db_cursor):
        """Document expected refresh_log schema contract."""
        db_cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'meta' AND table_name = 'refresh_log'
            """
        )
        columns = {row[0] for row in db_cursor.fetchall()}
        assert "source_id" in columns
        assert "source_name" in columns
        assert "status" in columns
        assert "records_fetched" in columns

    def test_get_last_successful_refresh(self, postgres_connection, db_cursor):
        """get_last_successful_refresh should return a datetime when present."""
        from dk_data.ingestion.main import get_last_successful_refresh

        db_cursor.execute(
            """
            INSERT INTO meta.data_sources
                (source_name, source_type, description, is_active, refresh_frequency)
            VALUES (%s, 'api', 'Integration test source', true, 'daily')
            ON CONFLICT (source_name) DO NOTHING
            """,
            (self.TEST_SOURCE,),
        )
        db_cursor.execute(
            "SELECT source_id FROM meta.data_sources WHERE source_name = %s",
            (self.TEST_SOURCE,),
        )
        source_id = db_cursor.fetchone()[0]
        db_cursor.execute(
            """
            INSERT INTO meta.refresh_log (
                source_id, source_name, refresh_started_at, refresh_completed_at,
                status, records_fetched, records_inserted, records_updated
            ) VALUES (%s, %s, NOW(), NOW(), 'success', 1, 1, 0)
            """,
            (source_id, self.TEST_SOURCE),
        )
        db_cursor.execute(
            """
            UPDATE meta.data_sources
            SET last_successful_refresh = NOW(), last_refresh_status = 'success'
            WHERE source_id = %s
            """,
            (source_id,),
        )
        postgres_connection.commit()

        try:
            value = get_last_successful_refresh(self.TEST_SOURCE)
            assert value is not None
            assert isinstance(value, datetime)
        finally:
            db_cursor.execute("DELETE FROM meta.refresh_log WHERE source_id = %s", (source_id,))
            db_cursor.execute("DELETE FROM meta.data_sources WHERE source_id = %s", (source_id,))
            postgres_connection.commit()

    def test_get_last_successful_refresh_missing_source(self):
        """Missing source should return None."""
        from dk_data.ingestion.main import get_last_successful_refresh

        assert get_last_successful_refresh("_nonexistent_xyz") is None
