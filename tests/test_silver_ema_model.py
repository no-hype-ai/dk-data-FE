"""Contract tests for Silver EMA SQLMesh model.

Feature: PR #415 Phase 1 (fix/415-phase1-db-first-router)
Task: Task 1.2 — Build mol_silver.ema (SQLMesh silver model)

Tests verify the silver/ema.sql file:
- Exists and is readable
- Contains correct MODEL declaration (name mol_silver.ema, kind FULL, grain, audits)
- Sources from bronze.ema (not mol_bronze.ema which does not exist)
- Yields all 14 mandatory output columns required by ema.py _db_query
- Follows silver antipattern rules (no S2 leading-wildcard LIKE, no banned inline fuzzy join)
- Uses NULL::UUID AS molecule_id (sibling-consistent entity resolution deferral)

These are static contract tests — they parse SQL files, not execute them.
"""

import re
from pathlib import Path

import pytest

from test_silver_model_contracts import _read_model_sql, _extract_model_block


MODELS_DIR = Path(__file__).resolve().parent.parent / "src" / "dk_data" / "sqlmesh" / "models" / "molecules"
SILVER_DIR = MODELS_DIR / "silver"

# The 14 mandatory output columns as required by ema.py _db_query
MANDATORY_COLUMNS = [
    "product_number",
    "product_name",
    "active_substance",
    "inn",
    "atc_code",
    "marketing_authorization_holder",
    "authorization_status",
    "authorization_date",
    "medicine_type",
    "therapeutic_area",
    "pharmacotherapeutic_group",
    "epar_url",
    "summary_url",
    "molecule_id",
]


class TestSilverEmaModel:
    """Contract tests for mol_silver.ema model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.sql = _read_model_sql("ema.sql")
        self.model_block = _extract_model_block(self.sql)

    # --- MODEL block declarations ---

    def test_model_name(self):
        """Model must declare name mol_silver.ema."""
        assert "name mol_silver.ema" in self.model_block

    def test_model_kind_full(self):
        """EMA authorizations are a complete vocabulary — FULL refresh is correct."""
        assert "FULL" in self.model_block

    def test_model_grain(self):
        """Grain is product_number (EMA authorisation number)."""
        assert "grain product_number" in self.model_block

    def test_model_audits_not_null(self):
        """Model must declare not_null audits on key columns."""
        assert "not_null" in self.model_block
        assert "product_number" in self.model_block
        assert "product_name" in self.model_block

    # --- Source reference ---

    def test_sources_from_bronze_ema(self):
        """Must source from bronze.ema (not mol_bronze.ema which does not exist)."""
        # Case-insensitive search; allow alias e.g. 'bronze.ema AS b' or 'bronze.ema b'
        assert re.search(r'FROM\s+bronze\.ema\b', self.sql, re.IGNORECASE), \
            "SQL must contain 'FROM bronze.ema' (not mol_bronze.ema)"

    def test_does_not_source_from_mol_bronze_ema(self):
        """Must NOT reference mol_bronze.ema — that table does not exist."""
        assert "mol_bronze.ema" not in self.sql.lower(), \
            "SQL must not reference mol_bronze.ema (dead reference — use bronze.ema)"

    # --- Mandatory output columns ---

    @pytest.mark.parametrize("col", MANDATORY_COLUMNS)
    def test_mandatory_column_present(self, col):
        """Each of the 14 columns required by ema.py _db_query must appear in the SELECT."""
        # Column name appears somewhere in SQL (as output identifier)
        assert re.search(rf'\b{re.escape(col)}\b', self.sql), \
            f"Mandatory output column '{col}' not found in SQL"

    # --- Silver antipattern guards ---

    def test_no_leading_wildcard_like_s2(self):
        """S2: Must not contain leading-wildcard LIKE patterns (LIKE '%' || ...)."""
        # Matches LIKE '%' or LIKE '' || pattern
        assert not re.search(r"LIKE\s+['\"]%", self.sql, re.IGNORECASE), \
            "S2 violation: leading-wildcard LIKE found"

    def test_no_inline_fuzzy_molecule_join_s1_s5(self):
        """S1/S5: Must not join mol_silver.molecules inline for molecule_id resolution."""
        assert "mol_silver.molecules" not in self.sql, \
            "Banned inline fuzzy join to mol_silver.molecules found (S1/S5 violation)"
        assert "canonical_name" not in self.sql, \
            "Banned inline fuzzy join using canonical_name found (S1/S5 violation)"

    def test_molecule_id_null_uuid_deferral(self):
        """molecule_id must use NULL::UUID deferral pattern (sibling-consistent)."""
        assert re.search(r'NULL::UUID\s+AS\s+molecule_id', self.sql, re.IGNORECASE), \
            "molecule_id must be expressed as NULL::UUID AS molecule_id (entity resolution deferred)"

    def test_no_nonexistent_bronze_columns(self):
        """Must not reference b.source or b.source_updated_at (not in bronze.ema schema)."""
        # Specifically check for the alias-prefixed nonexistent column refs from the worktree draft
        assert "b.source" not in self.sql, \
            "b.source does not exist in bronze.ema — remove or derive as literal"
        assert "b.source_updated_at" not in self.sql, \
            "b.source_updated_at does not exist in bronze.ema — remove or derive as literal"
