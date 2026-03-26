"""Contract tests for downstream API views.

Feature: 012-platform-hardening (US2)

Validates that db-init-job.yaml contains the expected API view definitions
with correct column references. These are structural tests — they verify
the SQL view definitions without requiring a database connection.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
DB_INIT_JOB = REPO_ROOT / "k8s" / "apps" / "infrastructure" / "base" / "db-init-job.yaml"


@pytest.fixture
def db_init_sql():
    """Load the db-init-job.yaml content."""
    return DB_INIT_JOB.read_text()


class TestAPIViewDefinitions:
    """Verify all 6 downstream API views are defined in db-init-job.yaml."""

    EXPECTED_VIEWS = [
        "api.company_pipeline",
        "api.molecule_targets",
        "api.trial_publication_features",
        "api.sider_side_effects",
        "api.bioactivity",
        "api.patents",
    ]

    @pytest.mark.parametrize("view_name", EXPECTED_VIEWS)
    def test_view_exists(self, db_init_sql, view_name):
        """Each API view must have a CREATE OR REPLACE VIEW statement."""
        assert f"CREATE OR REPLACE VIEW {view_name}" in db_init_sql, (
            f"Missing view definition for {view_name} in db-init-job.yaml"
        )

    @pytest.mark.parametrize("view_name", EXPECTED_VIEWS)
    def test_view_grant_exists(self, db_init_sql, view_name):
        """Each API view must have a GRANT SELECT — either literal or via dynamic format()."""
        # Check for literal GRANT statement
        has_literal_grant = f"GRANT SELECT ON {view_name}" in db_init_sql
        # Check for dynamic GRANT via format() — view name appears in the
        # conditional grants loop: IN ('company_pipeline', 'molecule_targets', ...)
        short_name = view_name.replace("api.", "")
        has_dynamic_grant = (
            f"'{short_name}'" in db_init_sql
            and "EXECUTE format('GRANT SELECT ON api.%I" in db_init_sql
        )
        assert has_literal_grant or has_dynamic_grant, (
            f"Missing GRANT for {view_name} in db-init-job.yaml"
        )


class TestCompanyPipelineView:
    """Verify company_pipeline view references real table columns."""

    def test_references_mol_gold_table(self, db_init_sql):
        assert "FROM mol_gold.company_pipeline" in db_init_sql

    def test_not_placeholder(self, db_init_sql):
        # Should NOT contain the old placeholder pattern for company_pipeline
        # The view should reference real columns, not NULL::text
        lines = db_init_sql.split("\n")
        in_company_view = False
        for line in lines:
            if "VIEW api.company_pipeline" in line:
                in_company_view = True
            elif in_company_view and "FROM mol_gold.company_pipeline" in line:
                break
            elif in_company_view and "WHERE false" in line:
                pytest.fail("company_pipeline still uses placeholder (WHERE false)")

    def test_has_required_columns(self, db_init_sql):
        for col in ["company_name", "molecule_name", "phase", "status"]:
            assert col in db_init_sql


class TestPatentsView:
    """Verify patents view references silver.patents, not placeholder."""

    def test_references_silver_table(self, db_init_sql):
        assert "FROM silver.patents" in db_init_sql

    def test_has_patent_number(self, db_init_sql):
        assert "patent_number" in db_init_sql


class TestTrialPublicationView:
    """Verify trial_publication_features view references real table."""

    def test_references_mol_gold_table(self, db_init_sql):
        assert "FROM mol_gold.trial_publication_features" in db_init_sql

    def test_has_required_columns(self, db_init_sql):
        for col in ["nct_id", "publication_doi", "overlap_score", "feature_type"]:
            assert col in db_init_sql


class TestMoleculeTargetsView:
    """Verify molecule_targets view exists with expected structure."""

    def test_references_mol_silver_table(self, db_init_sql):
        assert "FROM mol_silver.targets" in db_init_sql

    def test_has_required_columns(self, db_init_sql):
        for col in ["target_name", "target_type", "uniprot_accession", "gene_symbol"]:
            assert col in db_init_sql


class TestSiderView:
    """Verify sider_side_effects view exists."""

    def test_references_bronze_table(self, db_init_sql):
        assert "FROM bronze.sider" in db_init_sql


class TestBioactivityView:
    """Verify bioactivity view exists."""

    def test_references_silver_table(self, db_init_sql):
        assert "FROM silver.bioactivity" in db_init_sql
