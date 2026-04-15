"""Contract test: Bronze openfda_labels model covers all documented openFDA schema keys.

Reads the bronze openfda_labels SQLMesh model and asserts that every
documented openFDA Drug Labeling endpoint schema key has a matching
column projection.

Feature: 006-claims-engine-data-gaps (T082)
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BRONZE_MODEL = (
    REPO_ROOT
    / "src"
    / "dk_data"
    / "sqlmesh"
    / "models"
    / "molecules"
    / "bronze"
    / "openfda_labels.sql"
)

# Documented openFDA Drug Labeling schema keys
# Reference: https://open.fda.gov/apis/drug/label/searchable-fields/
# Grouped by category for clarity.

# Top-level label section keys (text content, extracted as ->>0)
LABEL_SECTION_KEYS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "boxed_warning",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "clinical_pharmacology",
    "mechanism_of_action",
    "pharmacodynamics",
    "pharmacokinetics",
    "overdosage",
    "description",
    "clinical_studies",
    "how_supplied",
    "storage_and_handling",
    "package_label_principal_display_panel",
    "pregnancy",
    "nursing_mothers",
    "pediatric_use",
    "geriatric_use",
    "abuse",
    "active_ingredient",
    "animal_pharmacology_and_or_toxicology",
    "carcinogenesis_and_mutagenesis_and_impairment_of_fertility",
    "controlled_substance",
    "dea_schedule",
    "dependence",
    "dosage_forms_and_strengths",
    "drug_abuse_and_dependence",
    "drug_and_or_laboratory_test_interactions",
    "inactive_ingredient",
    "information_for_patients",
    "instructions_for_use",
    "labor_and_delivery",
    "laboratory_tests",
    "microbiology",
    "nonclinical_toxicology",
    "nonteratogenic_effects",
    "precautions",
    "pregnancy_or_breast_feeding",
    "recent_major_changes",
    "references",
    "teratogenic_effects",
    # OTC sections
    "ask_doctor",
    "ask_doctor_or_pharmacist",
    "do_not_use",
    "keep_out_of_reach_of_children",
    "purpose",
    "questions",
    "stop_use",
    # SPL sections
    "spl_medguide",
    "spl_patient_package_insert",
    "spl_product_data_elements",
    "spl_unclassified_section",
]

# Table variant keys (JSONB)
TABLE_VARIANT_KEYS = [
    "adverse_reactions_table",
    "clinical_pharmacology_table",
    "clinical_studies_table",
    "description_table",
    "dosage_and_administration_table",
    "dosage_forms_and_strengths_table",
    "drug_interactions_table",
    "how_supplied_table",
    "instructions_for_use_table",
    "pharmacokinetics_table",
    "recent_major_changes_table",
    "spl_medguide_table",
    "spl_patient_package_insert_table",
    "spl_unclassified_section_table",
]

# openFDA sub-object keys (nested under label->'openfda')
OPENFDA_KEYS = [
    "brand_name",
    "generic_name",
    "manufacturer_name",
    "product_type",
    "substance_name",
    "route",
    "dosage_form",
    "pharm_class_epc",
    "pharm_class_moa",
    "pharm_class_pe",
    "pharm_class_cs",
    "product_ndc",
    "package_ndc",
    "original_packager_product_ndc",
    "upc",
    "spl_id",
    "rxcui",
    "unii",
    "spl_set_id",
    "nui",
    "application_number",
    "is_original_packager",
]

# Identifier keys
IDENTIFIER_KEYS = [
    "set_id",
    "version",  # mapped to spl_version
    "id",       # mapped to spl_id
    "effective_time",  # mapped to effective_date
]


@pytest.fixture
def model_sql() -> str:
    """Read the bronze openfda_labels model SQL."""
    assert BRONZE_MODEL.exists(), f"Bronze model not found at {BRONZE_MODEL}"
    return BRONZE_MODEL.read_text()


class TestOpenFDALabelCoverage:
    """Assert every documented openFDA schema key has a column projection."""

    def _extract_column_aliases(self, sql: str) -> set:
        """Extract all AS <alias> column names from the SELECT statement."""
        # Match "AS column_name" patterns (case-insensitive)
        aliases = set(re.findall(r'\bAS\s+(\w+)', sql, re.IGNORECASE))
        return aliases

    def _extract_json_paths(self, sql: str) -> set:
        """Extract all JSON field access paths from the SQL."""
        # Match label->>'field_name' and label->'field_name' patterns
        paths = set(re.findall(r"label->>?'(\w+)'", sql))
        # Also match label->'openfda'->'field' and label->'openfda'->>'field'
        openfda_paths = set(re.findall(r"openfda'->>?'(\w+)'", sql))
        return paths | openfda_paths

    def test_model_file_exists(self, model_sql: str):
        """Bronze openfda_labels model file must exist."""
        assert len(model_sql) > 100, "Model SQL appears empty or truncated"

    def test_label_section_keys_covered(self, model_sql: str):
        """Every documented label section key should appear in the model."""
        json_paths = self._extract_json_paths(model_sql)
        aliases = self._extract_column_aliases(model_sql)
        all_refs = json_paths | aliases

        missing = []
        for key in LABEL_SECTION_KEYS:
            # The key should appear either as a JSON path or as a column alias
            # Some keys are renamed in the projection (e.g., references -> label_references)
            if key not in all_refs and key not in model_sql:
                missing.append(key)

        assert not missing, (
            f"Label section keys missing from bronze openfda_labels model:\n"
            f"  {', '.join(sorted(missing))}"
        )

    def test_table_variant_keys_covered(self, model_sql: str):
        """Every documented table-variant key should appear in the model."""
        json_paths = self._extract_json_paths(model_sql)

        missing = [k for k in TABLE_VARIANT_KEYS if k not in json_paths]
        assert not missing, (
            f"Table variant keys missing from bronze openfda_labels model:\n"
            f"  {', '.join(sorted(missing))}"
        )

    def test_openfda_subobject_keys_covered(self, model_sql: str):
        """Every documented openfda sub-object key should appear in the model."""
        json_paths = self._extract_json_paths(model_sql)
        aliases = self._extract_column_aliases(model_sql)
        all_refs = json_paths | aliases

        missing = [k for k in OPENFDA_KEYS if k not in all_refs]
        assert not missing, (
            f"openFDA sub-object keys missing from bronze openfda_labels model:\n"
            f"  {', '.join(sorted(missing))}"
        )

    def test_identifier_keys_covered(self, model_sql: str):
        """Core identifier keys (set_id, version, id, effective_time) must appear."""
        json_paths = self._extract_json_paths(model_sql)

        missing = [k for k in IDENTIFIER_KEYS if k not in json_paths]
        assert not missing, (
            f"Identifier keys missing from bronze openfda_labels model:\n"
            f"  {', '.join(sorted(missing))}"
        )

    def test_has_boxed_warning_flag(self, model_sql: str):
        """Model should project a has_boxed_warning boolean flag."""
        aliases = self._extract_column_aliases(model_sql)
        assert "has_boxed_warning" in aliases, (
            "Expected has_boxed_warning flag in openfda_labels model"
        )

    def test_incremental_by_unique_key(self, model_sql: str):
        """Model should be INCREMENTAL_BY_UNIQUE_KEY on set_id."""
        assert "INCREMENTAL_BY_UNIQUE_KEY" in model_sql
        assert "set_id" in model_sql

    def test_source_tracking_columns(self, model_sql: str):
        """Model should include source tracking columns."""
        aliases = self._extract_column_aliases(model_sql)
        expected_tracking = {"source", "source_updated_at", "processed_to_silver"}
        missing = expected_tracking - aliases
        assert not missing, (
            f"Source tracking columns missing: {', '.join(sorted(missing))}"
        )
