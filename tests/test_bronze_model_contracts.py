"""Contract tests for Bronze SQLMesh models.

Feature: 014-uspto-euipo-model-datasource
Task: T027 — Bronze model contract tests

Tests verify that each bronze SQL model file:
- Exists and is readable
- Contains correct MODEL declaration (name, kind, grain, audits)
- Uses _loaded_at BETWEEN @start_dt AND @end_dt for incremental processing
- Has correct source table reference (raw.*)
- Contains expected output columns
- Has pharma classification logic (is_pharma_related)

These are static contract tests — they parse SQL files, not execute them.
"""

import re
from pathlib import Path

import pytest


MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "molecules"
BRONZE_DIR = MODELS_DIR / "bronze"


# ---------------------------------------------------------------------------
# Helper: parse MODEL block from SQLMesh SQL file
# ---------------------------------------------------------------------------

def _read_model_sql(filename: str) -> str:
    """Read a bronze model SQL file and return its contents."""
    filepath = BRONZE_DIR / filename
    assert filepath.exists(), f"Model file not found: {filepath}"
    return filepath.read_text()


def _extract_model_block(sql: str) -> str:
    """Extract the MODEL(...) block from SQL content."""
    match = re.search(r'MODEL\s*\((.*?)\);', sql, re.DOTALL)
    assert match, "MODEL block not found in SQL file"
    return match.group(1)


# ---------------------------------------------------------------------------
# bronze.uspto_patents — fix JSONB to flat column
# ---------------------------------------------------------------------------

class TestBronzeUSPTOPatents:
    """Contract tests for bronze.uspto_patents model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_patents.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name bronze.uspto_patents" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_time_column(self):
        assert "time_column ingested_at" in self.model_block

    def test_model_grain(self):
        assert "grain" in self.model_block
        assert "patent_number" in self.model_block

    def test_model_audits(self):
        assert "not_null" in self.model_block
        assert "unique_values" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM raw.uspto_patents" in self.sql

    def test_no_jsonb_extraction(self):
        """Core bug fix: no JSONB array extraction from response_body."""
        assert "response_body" not in self.sql
        assert "jsonb_array_elements" not in self.sql

    def test_output_columns(self):
        assert "r.patent_number" in self.sql
        assert "patent_title" in self.sql
        assert "patent_abstract" in self.sql
        assert "patent_date" in self.sql
        assert "cpc_codes" in self.sql
        assert "assignee_organization" in self.sql
        assert "num_claims" in self.sql
        assert "is_pharma_related" in self.sql
        assert "processed_to_silver" in self.sql
        assert "ingested_at" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_pharma_classification(self):
        assert "A61K" in self.sql
        assert "A61P" in self.sql

    def test_uses_gen_random_uuid(self):
        assert "gen_random_uuid()" in self.sql


# ---------------------------------------------------------------------------
# bronze.uspto_ci — NEW
# ---------------------------------------------------------------------------

class TestBronzeUSPTOCI:
    """Contract tests for bronze.uspto_ci model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_ci.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name bronze.uspto_ci" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "patent_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM raw.uspto_ci" in self.sql

    def test_patent_id_mapped_to_patent_number(self):
        """AC-2: patent_id is renamed to patent_number."""
        assert "r.patent_id AS patent_number" in self.sql

    def test_output_columns(self):
        assert "patent_title" in self.sql
        assert "patent_abstract" in self.sql
        assert "cpc_codes" in self.sql
        assert "is_pharma_related" in self.sql
        assert "ingested_at" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql


# ---------------------------------------------------------------------------
# bronze.epo_patents — NEW
# ---------------------------------------------------------------------------

class TestBronzeEPOPatents:
    """Contract tests for bronze.epo_patents model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("epo_patents.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name bronze.epo_patents" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "patent_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM raw.epo_patents" in self.sql

    def test_publication_id_mapped(self):
        """AC-2: publication_id is mapped to patent_number."""
        assert "r.publication_id AS patent_number" in self.sql

    def test_ipc_codes_preserved(self):
        """AC-3: IPC codes preserved in ipc_codes column."""
        assert "ipc_codes" in self.sql

    def test_family_id_preserved(self):
        assert "r.family_id" in self.sql

    def test_output_columns(self):
        assert "patent_title" in self.sql
        assert "patent_abstract" in self.sql
        assert "assignee_organization" in self.sql
        assert "is_pharma_related" in self.sql
        assert "ingested_at" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql


# ---------------------------------------------------------------------------
# bronze.uspto_trademarks — NEW
# ---------------------------------------------------------------------------

class TestBronzeUSPTOTrademarks:
    """Contract tests for bronze.uspto_trademarks model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_trademarks.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name bronze.uspto_trademarks" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "serial_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM raw.uspto_trademarks" in self.sql

    def test_output_columns(self):
        assert "r.serial_number" in self.sql
        assert "r.mark_element" in self.sql
        assert "r.mark_type" in self.sql
        assert "r.status" in self.sql
        assert "r.filing_date" in self.sql
        assert "r.owner_name" in self.sql
        assert "nice_classes" in self.sql
        assert "is_pharma_related" in self.sql
        assert "ingested_at" in self.sql

    def test_pharma_class_5(self):
        """AC-2: is_pharma_related is TRUE when Nice class 5 is present."""
        assert "5 = ANY" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql


# ---------------------------------------------------------------------------
# bronze.euipo_trademarks — NEW
# ---------------------------------------------------------------------------

class TestBronzeEUIPOTrademarks:
    """Contract tests for bronze.euipo_trademarks model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("euipo_trademarks.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name bronze.euipo_trademarks" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "application_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM raw.euipo_trademarks" in self.sql

    def test_euipo_specific_fields(self):
        """AC-2: EUIPO-specific fields are preserved."""
        assert "r.mark_kind" in self.sql
        assert "r.mark_feature" in self.sql
        assert "r.expiry_date" in self.sql

    def test_output_columns(self):
        assert "r.application_number" in self.sql
        assert "r.mark_name" in self.sql
        assert "r.applicant_name" in self.sql
        assert "r.status" in self.sql
        assert "r.filing_date" in self.sql
        assert "nice_classes" in self.sql
        assert "is_pharma_related" in self.sql
        assert "ingested_at" in self.sql

    def test_pharma_class_5(self):
        """AC-2: is_pharma_related is TRUE when Nice class 5 is present."""
        assert "5 = ANY" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql
