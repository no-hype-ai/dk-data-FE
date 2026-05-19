"""Contract tests for Gold SQLMesh models (Feature 015).

Feature: 015-assessment-dashboard-integration
Tasks: T047 (trial_outcomes), T053 (KOL/advocacy models)

Tests verify that each gold SQL model file:
- Exists and is readable
- Contains correct MODEL declaration (name, kind, grain, audits)
- Has correct source references
- Contains expected output columns
- Follows the model pattern (FULL vs INCREMENTAL_BY_UNIQUE_KEY)

These are static contract tests — they parse SQL files, not execute them.
"""

import re
from pathlib import Path

import pytest


GOLD_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "dk_data"
    / "sqlmesh"
    / "models"
    / "molecules"
    / "gold"
)


def _read_model_sql(filename: str) -> str:
    """Read a gold model SQL file and return its contents."""
    filepath = GOLD_DIR / filename
    assert filepath.exists(), f"Model file not found: {filepath}"
    return filepath.read_text()


def _extract_model_block(sql: str) -> str:
    """Extract the MODEL(...) block from SQL content."""
    match = re.search(r'MODEL\s*\((.*?)\);', sql, re.DOTALL)
    assert match, "MODEL block not found in SQL file"
    return match.group(1)


# ===========================================================================
# mol_gold.trial_outcomes — FULL model, UNION ALL of two evidence sources
# ===========================================================================


class TestGoldTrialOutcomes:
    """Contract tests for mol_gold.trial_outcomes model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("trial_outcomes.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.trial_outcomes" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_model_audits(self):
        assert "not_null" in self.model_block
        assert "evidence_source" in self.model_block
        assert "confidence_score" in self.model_block

    def test_union_all_structure(self):
        """Two-source UNION ALL: registry + publication."""
        assert "UNION ALL" in self.sql

    def test_registry_source(self):
        """Source 1: silver.clinical_trials with has_results."""
        assert "silver.clinical_trials" in self.sql
        assert "clinicaltrials_gov" in self.sql
        assert "has_results" in self.sql

    def test_publication_source(self):
        """Source 2: mol_silver.publication_evidence with confidence threshold."""
        assert "mol_silver.publication_evidence" in self.sql
        assert "'publication'" in self.sql

    def test_confidence_threshold(self):
        """Publication evidence filtered at >= 0.40 confidence."""
        assert "0.40" in self.sql

    def test_registry_confidence_score(self):
        """Registry outcomes have confidence_score = 1.0."""
        assert "1.0" in self.sql

    def test_output_columns(self):
        assert "molecule_id" in self.sql
        assert "trial_nct_id" in self.sql
        assert "evidence_source" in self.sql
        assert "endpoint_name" in self.sql
        assert "hazard_ratio" in self.sql
        assert "p_value" in self.sql
        assert "response_rate" in self.sql
        assert "sample_size" in self.sql
        assert "confidence_score" in self.sql
        assert "evidence_date" in self.sql


# ===========================================================================
# mol_gold.kol_profiles — INCREMENTAL_BY_UNIQUE_KEY, influence scoring
# ===========================================================================


class TestGoldKolProfiles:
    """Contract tests for mol_gold.kol_profiles model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("kol_profiles.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.kol_profiles" in self.model_block

    def test_model_kind(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_unique_key(self):
        assert "researcher_id" in self.model_block

    def test_reads_from_researchers(self):
        assert "silver.researchers" in self.sql

    def test_reads_from_publications(self):
        assert "silver.publications" in self.sql

    def test_reads_from_clinical_trials(self):
        assert "silver.clinical_trials" in self.sql

    def test_influence_formula_weights(self):
        """FR-018: h_index*0.3 + publications*0.2 + citations*0.25 + trials*0.15 + grants*0.1."""
        assert "0.3" in self.sql
        assert "0.2" in self.sql
        assert "0.25" in self.sql
        assert "0.15" in self.sql
        assert "0.1" in self.sql

    def test_influence_tier_thresholds(self):
        """Tier via PERCENT_RANK: >=0.95 Global, >=0.80 National, >=0.50 Regional, else Rising."""
        assert "0.95" in self.sql
        assert "0.80" in self.sql
        assert "0.50" in self.sql
        assert "'Global'" in self.sql
        assert "'National'" in self.sql
        assert "'Regional'" in self.sql
        assert "'Rising'" in self.sql

    def test_percent_rank_used(self):
        assert "PERCENT_RANK()" in self.sql

    def test_output_columns(self):
        assert "researcher_id" in self.sql
        assert "orcid_id" in self.sql
        assert "influence_score" in self.sql
        assert "influence_tier" in self.sql
        assert "h_index" in self.sql
        assert "publication_count" in self.sql
        assert "total_citations" in self.sql
        assert "trial_count" in self.sql


# ===========================================================================
# mol_gold.kol_network — FULL model, co-authorship edges
# ===========================================================================


class TestGoldKolNetwork:
    """Contract tests for mol_gold.kol_network model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("kol_network.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.kol_network" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_self_join_for_coauthorship(self):
        """Co-authorship via self-join on shared publications."""
        assert "source_researcher_id" in self.sql
        assert "target_researcher_id" in self.sql

    def test_connection_type(self):
        assert "'co_author'" in self.sql

    def test_shared_publications_count(self):
        assert "shared_publications" in self.sql

    def test_output_columns(self):
        assert "source_researcher_id" in self.sql
        assert "target_researcher_id" in self.sql
        assert "shared_publications" in self.sql
        assert "connection_type" in self.sql


# ===========================================================================
# mol_gold.kol_drug_associations — researcher-molecule mapping
# ===========================================================================


class TestGoldKolDrugAssociations:
    """Contract tests for mol_gold.kol_drug_associations model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("kol_drug_associations.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.kol_drug_associations" in self.model_block

    def test_model_kind(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_composite_unique_key(self):
        assert "researcher_id" in self.model_block
        assert "molecule_id" in self.model_block

    def test_trial_association_source(self):
        assert "silver.clinical_trials" in self.sql
        assert "'trial_investigator'" in self.sql

    def test_publication_association_source(self):
        assert "silver.publications" in self.sql
        assert "'publication_author'" in self.sql

    def test_output_columns(self):
        assert "researcher_id" in self.sql
        assert "molecule_id" in self.sql
        assert "drug_name" in self.sql
        assert "association_types" in self.sql
        assert "evidence_count" in self.sql


# ===========================================================================
# mol_gold.advocacy_groups — FULL model, derived from news signals
# ===========================================================================


class TestGoldAdvocacyGroups:
    """Contract tests for mol_gold.advocacy_groups model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("advocacy_groups.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.advocacy_groups" in self.model_block

    def test_model_kind_incremental(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_reads_from_news_signals(self):
        assert "silver.news_signals" in self.sql

    def test_output_columns(self):
        assert "group_id" in self.sql
        assert "organization_name" in self.sql
        assert "disease_focus" in self.sql
        assert "size_estimate" in self.sql
        assert "activities" in self.sql
        assert "indication" in self.sql


# ===========================================================================
# mol_gold.advocacy_sentiment — INCREMENTAL, per molecule-source sentiment
# ===========================================================================


class TestGoldAdvocacySentiment:
    """Contract tests for mol_gold.advocacy_sentiment model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("advocacy_sentiment.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.advocacy_sentiment" in self.model_block

    def test_model_kind(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_composite_unique_key(self):
        assert "molecule_id" in self.model_block
        assert "source" in self.model_block

    def test_reads_from_news_signals(self):
        assert "silver.news_signals" in self.sql

    def test_drug_mentions_linkage(self):
        """Links news signals to molecules via drug_mentions JSONB field."""
        assert "drug_mentions" in self.sql

    def test_output_columns(self):
        assert "molecule_id" in self.sql
        assert "source" in self.sql
        assert "sentiment_polarity" in self.sql
        assert "signal_count" in self.sql
        assert "recent_signals" in self.sql
        assert "time_period" in self.sql


# ===========================================================================
# mol_gold.regulatory_timeline — INCREMENTAL, cross-source regulatory
# ===========================================================================


class TestGoldRegulatoryTimeline:
    """Contract tests for mol_gold.regulatory_timeline model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("regulatory_timeline.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.regulatory_timeline" in self.model_block

    def test_model_kind(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_composite_unique_key(self):
        assert "molecule_id" in self.model_block
        assert "agency" in self.model_block
        assert "decision_date" in self.model_block

    def test_reads_from_regulatory_decisions(self):
        assert "silver.regulatory_decisions" in self.sql

    def test_molecule_linkage(self):
        assert "mol_silver.molecules" in self.sql

    def test_output_columns(self):
        assert "molecule_id" in self.sql
        assert "drug_name" in self.sql
        assert "agency" in self.sql
        assert "decision" in self.sql
        assert "decision_date" in self.sql
        assert "indication" in self.sql


# ===========================================================================
# mol_gold.financial_summary — INCREMENTAL, per molecule-company financials
# ===========================================================================


class TestGoldFinancialSummary:
    """Contract tests for mol_gold.financial_summary model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("financial_summary.sql")
        self.model_block = _extract_model_block(self.sql)

    def test_model_name(self):
        assert "name mol_gold.financial_summary" in self.model_block

    def test_model_kind(self):
        assert "INCREMENTAL_BY_UNIQUE_KEY" in self.model_block

    def test_composite_unique_key(self):
        assert "molecule_id" in self.model_block
        assert "cik" in self.model_block

    def test_reads_from_financial_data(self):
        assert "silver.financial_data" in self.sql

    def test_molecule_linkage(self):
        assert "mol_silver.molecules" in self.sql

    def test_output_columns(self):
        assert "molecule_id" in self.sql
        assert "company_name" in self.sql
        assert "cik" in self.sql
        assert "latest_revenue" in self.sql
        assert "latest_net_income" in self.sql
        assert "total_assets" in self.sql
        assert "filing_count" in self.sql
