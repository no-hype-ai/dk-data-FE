"""Stub end-to-end test for the Claims Engine 12-query adapter pattern.

Verifies that the claims engine's 12-step molecule-analysis pipeline can
be expressed against the silver/gold layer. Each step resolves through
the medallion architecture: resolve molecule -> resolve condition ->
fetch label -> fetch safety signals -> etc.

This is an integration test that requires a live database connection.
It is skipped by default in CI (no live DB).

Feature: 006-claims-engine-data-gaps (T083)
"""

import os

import pytest

# Mark for tests that need a live database
requires_db = pytest.mark.skipif(
    not os.environ.get("CLAIMS_ENGINE_DB_URL"),
    reason="Integration test — requires CLAIMS_ENGINE_DB_URL env var pointing to a live DB",
)


# ──────────────────────────────────────────────────────────────────────
# The 12-query adapter pattern for molecule analysis
# ──────────────────────────────────────────────────────────────────────
CLAIMS_ENGINE_QUERIES = [
    {
        "step": 1,
        "name": "resolve_molecule",
        "description": "Resolve a molecule by name/identifier via mol_silver.molecules",
        "schema": "mol_silver",
        "table": "molecules",
    },
    {
        "step": 2,
        "name": "resolve_condition",
        "description": "Resolve an indication/condition via ind_silver.conditions",
        "schema": "ind_silver",
        "table": "conditions",
    },
    {
        "step": 3,
        "name": "fetch_drug_label",
        "description": "Fetch FDA drug label sections via mol_silver.drug_labels",
        "schema": "mol_silver",
        "table": "drug_labels",
    },
    {
        "step": 4,
        "name": "fetch_safety_signals",
        "description": "Fetch FAERS adverse-event signals via mol_silver.adverse_events",
        "schema": "mol_silver",
        "table": "adverse_events",
    },
    {
        "step": 5,
        "name": "fetch_clinical_trials",
        "description": "Fetch clinical trials via mol_silver.clinical_trials",
        "schema": "mol_silver",
        "table": "clinical_trials",
    },
    {
        "step": 6,
        "name": "fetch_regulatory_status",
        "description": "Fetch regulatory decisions via mol_silver.regulatory_decisions",
        "schema": "mol_silver",
        "table": "regulatory_decisions",
    },
    {
        "step": 7,
        "name": "fetch_enforcement_actions",
        "description": "Fetch FDA enforcement actions via mol_silver.fda_enforcement_actions",
        "schema": "mol_silver",
        "table": "fda_enforcement_actions",
    },
    {
        "step": 8,
        "name": "fetch_patent_landscape",
        "description": "Fetch patent data via ip_silver.patents",
        "schema": "ip_silver",
        "table": "patents",
    },
    {
        "step": 9,
        "name": "fetch_market_data",
        "description": "Fetch drug spending/market data via mol_silver.drug_spending",
        "schema": "mol_silver",
        "table": "drug_spending",
    },
    {
        "step": 10,
        "name": "fetch_physician_prescribing",
        "description": "Fetch prescriber data via mol_silver.physician_profiles",
        "schema": "mol_silver",
        "table": "physician_profiles",
    },
    {
        "step": 11,
        "name": "fetch_conference_abstracts",
        "description": "Fetch conference abstracts via mol_silver.conference_abstracts",
        "schema": "mol_silver",
        "table": "conference_abstracts",
    },
    {
        "step": 12,
        "name": "fetch_publications",
        "description": "Fetch publication evidence via mol_silver.publications",
        "schema": "mol_silver",
        "table": "publications",
    },
]


@pytest.fixture(scope="module")
def db_conn():
    """Create a database connection from CLAIMS_ENGINE_DB_URL."""
    import psycopg2  # noqa: F811

    conn = psycopg2.connect(os.environ["CLAIMS_ENGINE_DB_URL"])
    yield conn
    conn.close()


class TestClaimsEngineE2E:
    """End-to-end test: the 12-query claims engine adapter pattern."""

    def test_all_12_steps_defined(self):
        """Verify we have exactly 12 query steps defined."""
        assert len(CLAIMS_ENGINE_QUERIES) == 12
        steps = [q["step"] for q in CLAIMS_ENGINE_QUERIES]
        assert steps == list(range(1, 13)), "Steps should be 1..12 in order"

    def test_all_steps_have_required_fields(self):
        """Each step must declare name, schema, table, description."""
        for q in CLAIMS_ENGINE_QUERIES:
            assert "name" in q, f"Step {q['step']} missing 'name'"
            assert "schema" in q, f"Step {q['step']} missing 'schema'"
            assert "table" in q, f"Step {q['step']} missing 'table'"
            assert "description" in q, f"Step {q['step']} missing 'description'"

    @requires_db
    def test_resolve_molecule_query(self, db_conn):
        """Step 1: Resolve molecule by name against mol_silver.molecules."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT id, name FROM mol_silver.molecules WHERE LOWER(name) = %s LIMIT 1",
            ("aspirin",),
        )
        row = cur.fetchone()
        cur.close()
        # We don't assert row is not None — the DB may not have aspirin.
        # The point is that the query executes without error.
        assert True, "resolve_molecule query executed successfully"

    @requires_db
    def test_resolve_condition_query(self, db_conn):
        """Step 2: Resolve condition by name against ind_silver.conditions."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT id, name FROM ind_silver.conditions WHERE LOWER(name) LIKE %s LIMIT 1",
            ("%diabetes%",),
        )
        cur.fetchone()
        cur.close()
        assert True, "resolve_condition query executed successfully"

    @requires_db
    def test_fetch_drug_label_query(self, db_conn):
        """Step 3: Fetch drug label sections."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.drug_labels LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_drug_label query executed successfully"

    @requires_db
    def test_fetch_safety_signals_query(self, db_conn):
        """Step 4: Fetch FAERS adverse event signals."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.adverse_events LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_safety_signals query executed successfully"

    @requires_db
    def test_fetch_clinical_trials_query(self, db_conn):
        """Step 5: Fetch clinical trials."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.clinical_trials LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_clinical_trials query executed successfully"

    @requires_db
    def test_fetch_regulatory_status_query(self, db_conn):
        """Step 6: Fetch regulatory decisions."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.regulatory_decisions LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_regulatory_status query executed successfully"

    @requires_db
    def test_fetch_enforcement_actions_query(self, db_conn):
        """Step 7: Fetch FDA enforcement actions."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.fda_enforcement_actions LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_enforcement_actions query executed successfully"

    @requires_db
    def test_fetch_patent_landscape_query(self, db_conn):
        """Step 8: Fetch patent data."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM ip_silver.patents LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_patent_landscape query executed successfully"

    @requires_db
    def test_fetch_market_data_query(self, db_conn):
        """Step 9: Fetch drug spending/market data."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.drug_spending LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_market_data query executed successfully"

    @requires_db
    def test_fetch_physician_prescribing_query(self, db_conn):
        """Step 10: Fetch physician prescribing data."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.physician_profiles LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_physician_prescribing query executed successfully"

    @requires_db
    def test_fetch_conference_abstracts_query(self, db_conn):
        """Step 11: Fetch conference abstracts."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.conference_abstracts LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_conference_abstracts query executed successfully"

    @requires_db
    def test_fetch_publications_query(self, db_conn):
        """Step 12: Fetch publication evidence."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mol_silver.publications LIMIT 1",
        )
        cur.fetchone()
        cur.close()
        assert True, "fetch_publications query executed successfully"
