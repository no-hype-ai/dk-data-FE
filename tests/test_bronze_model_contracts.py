"""Contract tests for Bronze SQLMesh models.

Feature: 014-uspto-euipo-model-datasource
Task: T027 — Bronze model contract tests

Tests verify that each bronze SQL model file:
- Exists and is readable
- Contains correct MODEL declaration (name, kind, grain, audits)
- Uses appropriate incremental filter for its model kind
- Has correct source table reference
- Contains expected output columns

These are static contract tests — they parse SQL files, not execute them.

Schema naming convention (019-cms-puf-platform-reconciliation):
  mol_bronze / mol_raw — Molecule / drug / compound data
  hcs_bronze / hcs_raw — Healthcare system / CMS / provider data
"""

import re
from pathlib import Path

import pytest


MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "molecules"
BRONZE_DIR = MODELS_DIR / "bronze"

HCS_MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "hcs"
HCS_BRONZE_DIR = HCS_MODELS_DIR / "bronze"


# ---------------------------------------------------------------------------
# Helper: parse MODEL block from SQLMesh SQL file
# ---------------------------------------------------------------------------

def _read_model_sql(filename: str) -> str:
    """Read a mol bronze model SQL file and return its contents."""
    filepath = BRONZE_DIR / filename
    assert filepath.exists(), f"Model file not found: {filepath}"
    return filepath.read_text()


def _read_hcs_model_sql(filename: str) -> str:
    """Read an hcs bronze model SQL file and return its contents."""
    filepath = HCS_BRONZE_DIR / filename
    assert filepath.exists(), f"HCS model file not found: {filepath}"
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
    """Contract tests for mol_bronze.uspto_patents model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_patents.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.uspto_patents" in self.model_block

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
        assert "FROM mol_raw.uspto_patents" in self.sql

    def test_no_jsonb_extraction(self):
        """Core bug fix: no JSONB array extraction from response_body; cpc_codes converted via to_jsonb."""
        assert "response_body" not in self.sql
        # Old bad patterns removed: CASE WHEN conditional to_jsonb and unnest with COALESCE on mixed types
        assert "CASE WHEN r.cpc_codes IS NOT NULL THEN to_jsonb" not in self.sql
        assert "unnest(COALESCE(r.cpc_codes" not in self.sql

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
    """Contract tests for mol_bronze.uspto_ci model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_ci.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.uspto_ci" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "patent_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.uspto_ci" in self.sql

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
    """Contract tests for mol_bronze.epo_patents model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("epo_patents.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.epo_patents" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "patent_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.epo_patents" in self.sql

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
    """Contract tests for mol_bronze.uspto_trademarks model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("uspto_trademarks.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.uspto_trademarks" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "serial_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.uspto_trademarks" in self.sql

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
        """AC-2: is_pharma_related is TRUE when Nice class 5 is present.
        mol_raw.uspto_trademarks.nice_classes is JSONB, so detection uses
        JSONB containment (@>) rather than = ANY(array).
        """
        # JSONB containment: nice_classes @> '[5]'::JSONB
        assert "'[5]'" in self.sql or "@>" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql


# ---------------------------------------------------------------------------
# bronze.euipo_trademarks — NEW
# ---------------------------------------------------------------------------

class TestBronzeEUIPOTrademarks:
    """Contract tests for mol_bronze.euipo_trademarks model.

    Note: mol_raw.euipo_trademarks.nice_classes is JSONB (not TEXT[]/INT[]),
    so pharma-class detection uses JSONB containment (@>) instead of = ANY().
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("euipo_trademarks.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.euipo_trademarks" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "application_number" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.euipo_trademarks" in self.sql

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
        """AC-2: is_pharma_related uses JSONB containment for Nice class 5 (JSONB column)."""
        # nice_classes is JSONB in mol_raw.euipo_trademarks, so we use @> not = ANY()
        assert "is_pharma_related" in self.sql
        assert "[5]" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql


# ===========================================================================
# Feature 015: Assessment Dashboard Integration — bronze models
# ===========================================================================
# Models split into two groups:
#   True JSONB: extract from response_body, INCREMENTAL_BY_TIME_RANGE,
#               time_column request_timestamp, filter on processed_to_bronze/response_status
#   Flat-column: typed raw columns, INCREMENTAL_BY_UNIQUE_KEY or TIME_RANGE with _loaded_at
# ===========================================================================


class _BronzeJSONBModelTestBase:
    """Base test class for bronze models that extract from JSONB response_body.

    Applies to: pdb_structures, who_icd, cms_inpatient, acc_tvc, hrsa.
    """

    MODEL_FILE: str = ""
    MODEL_NAME: str = ""
    GRAIN_COLUMN: str = ""
    RAW_TABLE: str = ""
    EXPECTED_COLUMNS: list = []

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql(self.MODEL_FILE)
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert f"name {self.MODEL_NAME}" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_time_column(self):
        assert "time_column request_timestamp" in self.model_block

    def test_model_grain(self):
        assert self.GRAIN_COLUMN in self.model_block

    def test_reads_from_correct_raw_table(self):
        assert f"FROM {self.RAW_TABLE}" in self.sql

    def test_jsonb_extraction(self):
        """JSONB envelope models should extract from response_body."""
        assert "response_body" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "request_timestamp BETWEEN @start_dt AND @end_dt" in self.sql

    def test_processed_to_bronze_filter(self):
        assert "processed_to_bronze = FALSE" in self.sql

    def test_response_status_filter(self):
        assert "response_status = 200" in self.sql

    def test_expected_output_columns(self):
        for col in self.EXPECTED_COLUMNS:
            assert col in self.sql, f"Expected column '{col}' not found in {self.MODEL_FILE}"


# ---------------------------------------------------------------------------
# True JSONB models (pdb_structures, who_icd) — mol_raw / mol_bronze
# ---------------------------------------------------------------------------

class TestBronzePdbStructures(_BronzeJSONBModelTestBase):
    MODEL_FILE = "pdb_structures.sql"
    MODEL_NAME = "mol_bronze.pdb_structures"
    GRAIN_COLUMN = "pdb_id"
    RAW_TABLE = "mol_raw.pdb"
    EXPECTED_COLUMNS = ["pdb_id", "title", "resolution", "method", "organism", "ligand_id", "ligand_name", "uniprot_id"]


class TestBronzeWhoIcd(_BronzeJSONBModelTestBase):
    MODEL_FILE = "who_icd.sql"
    MODEL_NAME = "mol_bronze.who_icd"
    GRAIN_COLUMN = "icd_code"
    RAW_TABLE = "mol_raw.who_icd"
    EXPECTED_COLUMNS = ["icd_code", "title", "class_kind", "definition", "inclusion_terms", "exclusion_terms"]


# ---------------------------------------------------------------------------
# True JSONB models (cms_inpatient, acc_tvc, hrsa) — hcs_raw / hcs_bronze
# ---------------------------------------------------------------------------

class TestBronzeCmsInpatient:
    """hcs_bronze.cms_inpatient — flat typed columns from hcs_raw.cms_inpatient_puf."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_hcs_model_sql("cms_inpatient.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name hcs_bronze.cms_inpatient" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "record_id" in self.model_block

    def test_reads_from_correct_raw_table(self):
        assert "hcs_raw.cms_inpatient_puf" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "@start_dt" in self.sql and "@end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["provider_id", "drg_code", "total_discharges", "avg_charges", "avg_payments", "fiscal_year"]:
            assert col in self.sql, f"Expected column '{col}' not found in cms_inpatient.sql"


class TestBronzeAccTvc:
    """hcs_bronze.acc_tvc — flat typed columns from hcs_raw.acc_tvc_certification."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_hcs_model_sql("acc_tvc.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name hcs_bronze.acc_tvc" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "facility_name" in self.model_block

    def test_reads_from_correct_raw_table(self):
        assert "hcs_raw.acc_tvc_certification" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "@start_dt" in self.sql and "@end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["facility_name", "city", "state", "certification_type", "certification_date", "expiration_date"]:
            assert col in self.sql, f"Expected column '{col}' not found in acc_tvc.sql"


class TestBronzeHrsa:
    """hcs_bronze.hrsa — flat typed columns from hcs_raw.hrsa_shortage_areas."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_hcs_model_sql("hrsa.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name hcs_bronze.hrsa" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_grain(self):
        assert "hpsa_id" in self.model_block

    def test_reads_from_correct_raw_table(self):
        assert "hcs_raw.hrsa_shortage_areas" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "@start_dt" in self.sql and "@end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["hpsa_id", "designation_type", "state", "county", "discipline", "score", "status"]:
            assert col in self.sql, f"Expected column '{col}' not found in hrsa.sql"


# ---------------------------------------------------------------------------
# Flat-column mol_bronze models — INCREMENTAL_BY_UNIQUE_KEY, _loaded_at filter
# ---------------------------------------------------------------------------

class TestBronzePubmed:
    """mol_bronze.pubmed — flat typed columns from mol_raw.pubmed."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("pubmed.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.pubmed" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "pmid" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.pubmed" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["pmid", "title", "abstract", "authors", "journal", "publication_date", "mesh_terms", "doi"]:
            assert col in self.sql, f"Expected column '{col}' not found in pubmed.sql"


class TestBronzeCochraneReviews:
    """mol_bronze.cochrane_reviews — flat typed columns from mol_raw.cochrane_reviews."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("cochrane_reviews.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.cochrane_reviews" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "review_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.cochrane_reviews" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["review_id", "title", "authors", "abstract", "publication_date", "doi", "review_type"]:
            assert col in self.sql, f"Expected column '{col}' not found in cochrane_reviews.sql"


class TestBronzeHTADecisions:
    """mol_bronze.hta_decisions — flat typed columns from mol_raw.hta_decisions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("hta_decisions.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.hta_decisions" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "decision_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.hta_decisions" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["agency", "drug_name", "indication", "decision_type", "decision_date", "document_url", "summary"]:
            assert col in self.sql, f"Expected column '{col}' not found in hta_decisions.sql"


class TestBronzeSecEdgar:
    """mol_bronze.sec_edgar — flat typed columns from mol_raw.sec_edgar."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("sec_edgar.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.sec_edgar" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "filing_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.sec_edgar" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["cik", "company_name", "filing_type", "filing_date", "revenue", "net_income", "total_assets"]:
            assert col in self.sql, f"Expected column '{col}' not found in sec_edgar.sql"


class TestBronzeOrcid:
    """mol_bronze.orcid — JSONB extraction, INCREMENTAL_BY_TIME_RANGE with fetched_at."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("orcid.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.orcid" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_time_column(self):
        assert "time_column fetched_at" in self.model_block

    def test_model_grain(self):
        assert "orcid_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.orcid" in self.sql

    def test_jsonb_extraction(self):
        assert "response_body" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "fetched_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["orcid_id", "given_name", "family_name", "affiliations", "works_count", "research_areas"]:
            assert col in self.sql, f"Expected column '{col}' not found in orcid.sql"


class TestBronzeJournalRss:
    """mol_bronze.journal_rss — flat typed columns, INCREMENTAL_BY_TIME_RANGE with _loaded_at."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("journal_rss.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.journal_rss" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_time_column(self):
        assert "time_column _loaded_at" in self.model_block

    def test_model_grain(self):
        assert "article_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.journal_rss" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["title", "link", "pub_date", "feed_source", "abstract", "authors", "doi"]:
            assert col in self.sql, f"Expected column '{col}' not found in journal_rss.sql"


class TestBronzeMedicalNews:
    """mol_bronze.medical_news — flat typed columns, INCREMENTAL_BY_TIME_RANGE with _loaded_at."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("medical_news.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_bronze.medical_news" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_TIME_RANGE" in self.model_block

    def test_model_time_column(self):
        assert "time_column _loaded_at" in self.model_block

    def test_model_grain(self):
        assert "article_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "FROM mol_raw.medical_news" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["title", "url", "pub_date", "source_name", "summary", "drug_mentions", "therapeutic_areas"]:
            assert col in self.sql, f"Expected column '{col}' not found in medical_news.sql"


# ---------------------------------------------------------------------------
# Flat-column hcs_bronze models — INCREMENTAL_BY_UNIQUE_KEY, _loaded_at filter
# ---------------------------------------------------------------------------

class TestBronzeCmsHospitalInfo:
    """hcs_bronze.cms_hospital_info — flat typed columns from hcs_raw.cms_hospital_general_info."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_hcs_model_sql("cms_hospital_info.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name hcs_bronze.cms_hospital_info" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "provider_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "hcs_raw.cms_hospital_general_info" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["provider_id", "hospital_name", "city", "state", "hospital_type", "ownership", "rating"]:
            assert col in self.sql, f"Expected column '{col}' not found in cms_hospital_info.sql"


class TestBronzeCmsCostReports:
    """hcs_bronze.cms_cost_reports — flat typed columns from hcs_raw.cms_cost_reports_puf."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_hcs_model_sql("cms_cost_reports.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name hcs_bronze.cms_cost_reports" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_grain(self):
        assert "provider_id" in self.model_block

    def test_reads_from_raw_table(self):
        assert "hcs_raw.cms_cost_reports_puf" in self.sql

    def test_processed_to_silver_output(self):
        assert "processed_to_silver" in self.sql

    def test_incremental_filter(self):
        assert "_loaded_at BETWEEN @start_dt AND @end_dt" in self.sql

    def test_expected_output_columns(self):
        for col in ["provider_id", "fiscal_year_begin", "total_operating_expenses", "net_patient_revenue", "operating_margin", "bed_count"]:
            assert col in self.sql, f"Expected column '{col}' not found in cms_cost_reports.sql"
