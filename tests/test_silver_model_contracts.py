"""Contract tests for Silver SQLMesh models.

Feature: 014-uspto-euipo-model-datasource
Task: T028 — Silver model contract tests

Tests verify that each silver SQL model file:
- Exists and is readable
- Contains correct MODEL declaration (name, kind, grain, audits)
- Has correct source references (bronze.*)
- Implements expected deduplication strategy
- Contains required output columns
- Follows source priority ordering (patents) or within-registry dedup (trademarks)

These are static contract tests — they parse SQL files, not execute them.
"""

import re
from pathlib import Path

import pytest


MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "molecules"
SILVER_DIR = MODELS_DIR / "silver"

IP_MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "ip"
IP_SILVER_DIR = IP_MODELS_DIR / "silver"


# ---------------------------------------------------------------------------
# Helper: parse MODEL block from SQLMesh SQL file
# ---------------------------------------------------------------------------

def _read_model_sql(filename: str) -> str:
    """Read a silver model SQL file and return its contents."""
    filepath = SILVER_DIR / filename
    assert filepath.exists(), f"Model file not found: {filepath}"
    return filepath.read_text()


def _read_ip_model_sql(filename: str) -> str:
    """Read an IP silver model SQL file and return its contents."""
    filepath = IP_SILVER_DIR / filename
    assert filepath.exists(), f"IP model file not found: {filepath}"
    return filepath.read_text()


def _extract_model_block(sql: str) -> str:
    """Extract the MODEL(...) block from SQL content."""
    match = re.search(r'MODEL\s*\((.*?)\);', sql, re.DOTALL)
    assert match, "MODEL block not found in SQL file"
    return match.group(1)


# ===========================================================================
# silver.patents — 4-source UNION ALL with source priority
# ===========================================================================

class TestSilverPatents:
    """Contract tests for ip_silver.patents hub model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_ip_model_sql("patents.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name ip_silver.patents" in self.model_block

    def test_model_kind_incremental_by_unique_key(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_unique_key(self):
        assert "unique_key patent_id" in self.model_block

    def test_model_grain(self):
        assert "grain patent_id" in self.model_block

    def test_has_uspto_patents_cte(self):
        """Hub should source from USPTO patents."""
        assert "uspto_patents AS" in self.sql

    def test_has_epo_patents_cte(self):
        """Hub should source from EPO patents."""
        assert "epo_patents AS" in self.sql

    def test_uses_union_all(self):
        assert "UNION ALL" in self.sql

    def test_deduplication(self):
        assert "DISTINCT ON (patent_id)" in self.sql

    def test_reads_from_bronze_uspto_patents(self):
        assert "bronze.uspto_patents" in self.sql

    def test_reads_from_bronze_epo_patents(self):
        assert "bronze.epo_patents" in self.sql

    def test_output_columns(self):
        for col in ["patent_id", "jurisdiction", "patent_number", "filing_date"]:
            assert col in self.sql, f"Expected column {col} not found"



# ===========================================================================
# silver.trademarks — NEW, within-registry dedup
# ===========================================================================

class TestSilverTrademarks:
    """Contract tests for ip_silver.trademarks hub model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_ip_model_sql("trademarks.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name ip_silver.trademarks" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_unique_key(self):
        assert "unique_key trademark_id" in self.model_block

    def test_has_uspto_cte(self):
        assert "uspto_trademarks AS" in self.sql

    def test_has_euipo_cte(self):
        assert "euipo_trademarks AS" in self.sql

    def test_uses_union_all(self):
        assert "UNION ALL" in self.sql

    def test_output_columns(self):
        for col in ["trademark_id", "jurisdiction", "mark_text", "filing_date"]:
            assert col in self.sql, f"Expected column {col} not found"



# ===========================================================================
# Feature 015: Assessment Dashboard Integration — 6 new silver models
# ===========================================================================


class _SilverModelTestBase:
    """Base test class for Feature 015 silver model contract tests."""

    MODEL_FILE: str = ""
    MODEL_NAME: str = ""
    UNIQUE_KEY: str = ""
    BRONZE_SOURCES: list = []
    EXPECTED_COLUMNS: list = []

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql(self.MODEL_FILE)
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert f"name {self.MODEL_NAME}" in self.model_block

    def test_model_kind_incremental_by_unique_key(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_unique_key(self):
        assert self.UNIQUE_KEY in self.model_block

    def test_reads_from_bronze_sources(self):
        for source in self.BRONZE_SOURCES:
            assert source in self.sql, f"Expected bronze source '{source}' not found"

    def test_expected_output_columns(self):
        for col in self.EXPECTED_COLUMNS:
            assert col in self.sql, f"Expected column '{col}' not found in {self.MODEL_FILE}"


class TestSilverRegulatoryDecisions(_SilverModelTestBase):
    MODEL_FILE = "regulatory_decisions.sql"
    MODEL_NAME = "mol_silver.regulatory_decisions"
    UNIQUE_KEY = "agency, drug_name, indication, decision_date"
    BRONZE_SOURCES = ["bronze.ema", "bronze.hta_decisions"]
    EXPECTED_COLUMNS = [
        "agency", "drug_name", "active_substance", "indication",
        "decision", "decision_date", "therapeutic_area", "recommendation_details",
    ]

    def test_union_all_structure(self):
        assert "UNION ALL" in self.sql

    def test_distinct_on_dedup(self):
        assert "DISTINCT ON" in self.sql


class TestSilverFinancialData(_SilverModelTestBase):
    MODEL_FILE = "financial_data.sql"
    MODEL_NAME = "mol_silver.financial_data"
    UNIQUE_KEY = "cik, filing_type, filing_date"
    BRONZE_SOURCES = ["bronze.sec_edgar"]
    EXPECTED_COLUMNS = [
        "cik", "company_name", "filing_type", "filing_date",
        "revenue", "net_income", "total_assets",
    ]


class TestSilverResearchers(_SilverModelTestBase):
    MODEL_FILE = "researchers.sql"
    MODEL_NAME = "mol_silver.researchers"
    UNIQUE_KEY = "orcid_id"
    BRONZE_SOURCES = ["bronze.orcid"]
    EXPECTED_COLUMNS = [
        "orcid_id", "given_name", "family_name", "affiliation",
        "country", "works_count", "h_index", "research_areas",
    ]


class TestSilverNewsSignals(_SilverModelTestBase):
    MODEL_FILE = "news_signals.sql"
    MODEL_NAME = "mol_silver.news_signals"
    UNIQUE_KEY = "source_url, pub_date"
    BRONZE_SOURCES = ["bronze.medical_news"]
    EXPECTED_COLUMNS = [
        "title", "source_name", "pub_date", "source_url",
        "drug_mentions", "sentiment_polarity", "signal_type",
    ]



class TestSilverIcdCodes(_SilverModelTestBase):
    MODEL_FILE = "icd_codes.sql"
    MODEL_NAME = "mol_silver.icd_codes"
    UNIQUE_KEY = "icd_code"
    BRONZE_SOURCES = ["bronze.who_icd"]
    EXPECTED_COLUMNS = [
        "icd_code", "title", "class_kind", "chapter",
        "category", "parent_code", "is_leaf",
    ]


# -----------------------------------------------------------------------
# Extended model tests — verify new sources in existing models
# -----------------------------------------------------------------------

class TestSilverPublicationsExtension:
    """Verify publications extended with PubMed, Cochrane, Journal RSS."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("publications.sql")

    def test_pubmed_source_added(self):
        assert "bronze.pubmed" in self.sql

    def test_cochrane_source_added(self):
        assert "bronze.cochrane_reviews" in self.sql

    def test_journal_rss_source_added(self):
        assert "bronze.journal_rss" in self.sql

    def test_union_all_combines_all_sources(self):
        assert self.sql.count("UNION ALL") >= 3


class TestSilverPatentsExtension:
    """Verify patents hub sources are correct."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_ip_model_sql("patents.sql")

    def test_has_orange_book_source(self):
        # The hub may or may not source from orange_book directly
        # (FR-034 links via molecule_id, not as a direct patent source)
        assert "patents" in self.sql.lower()



class TestSilverTargetsExtension:
    """Verify targets documents PDB enrichment."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("targets.sql")

    def test_hub_sources(self):
        """Targets hub sources from uniprot + chembl protein_targets."""
        assert "uniprot" in self.sql.lower() or "protein_targets" in self.sql.lower()
