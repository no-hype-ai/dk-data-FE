"""
T080: Bootstrap smoke tests — validate schema infrastructure is in place.

These are integration tests that verify the DB schema is ready for bootstrap
procedures to run. They do NOT execute the bootstrap procedures themselves
(that is operational work). They confirm:
- All 10 bootstrap stored procedures exist in pg_proc
- meta.job_locks has expected columns
- meta.refresh_state has expected columns
- meta.transform_runs has expected columns
- The bootstrap execution order is documented and correct
"""
import pytest


pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Expected procedures in dependency/tier order (Tier 0 → Tier 1 → Tier 2+)
# ---------------------------------------------------------------------------
BOOTSTRAP_PROCEDURES = [
    # Schema,    Procedure name
    ("hcs_silver", "bootstrap_facilities"),       # Tier 0 — ~6K rows
    ("mol_silver", "bootstrap_companies"),        # Tier 0 — ~10K rows
    ("ind_silver", "bootstrap_conditions"),       # Tier 0 — ~50K rows
    ("mol_silver", "bootstrap_targets"),          # Tier 1 — ~500K rows
    ("mol_silver", "bootstrap_molecules"),        # Tier 1 — ~500K rows
    ("ip_silver",  "bootstrap_designs"),          # Tier 1 — ~3M rows
    ("mol_silver", "bootstrap_drug_products"),    # Tier 1/2
    ("ip_silver",  "bootstrap_trademarks"),       # Tier 2 — ~12M rows
    ("ip_silver",  "bootstrap_patents"),          # Tier 2 — ~5M rows
    ("hcs_silver", "bootstrap_providers"),        # LARGEST — ~10M rows
    ("hcp_silver", "bootstrap_researchers"),      # ~2M rows
    ("hcp_silver", "bootstrap_researcher_provider_crosswalk"),  # depends on providers + researchers
]


class TestProcedureExists:
    """Each bootstrap procedure must be registered in pg_proc."""

    @pytest.mark.parametrize("schema,proc_name", BOOTSTRAP_PROCEDURES)
    def test_procedure_exists(self, db_cursor, schema, proc_name):
        """Verify that CALL <schema>.<proc_name>() is resolvable in pg_proc."""
        db_cursor.execute(
            """
            SELECT COUNT(*) FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = %s
              AND p.proname = %s
              AND p.prokind = 'p'   -- 'p' = procedure (not function)
            """,
            (schema, proc_name),
        )
        count = db_cursor.fetchone()[0]
        assert count == 1, (
            f"Procedure {schema}.{proc_name}() not found in pg_proc. "
            "Run the 014–023b migrations first."
        )


class TestMetaJobLocksSchema:
    """meta.job_locks must have the columns required by the bootstrap lock pattern."""

    EXPECTED_COLUMNS = {"name", "locked_by", "locked_at", "expires_at"}

    def test_meta_job_locks_schema(self, db_cursor):
        db_cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'meta'
              AND table_name   = 'job_locks'
            """
        )
        actual = {row[0] for row in db_cursor.fetchall()}
        missing = self.EXPECTED_COLUMNS - actual
        assert not missing, (
            f"meta.job_locks is missing columns: {missing}. "
            f"Existing columns: {actual}"
        )

    def test_meta_job_locks_pk_is_name(self, db_cursor):
        """The primary key of meta.job_locks must be the 'name' column."""
        db_cursor.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = tc.constraint_name
                AND kcu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'meta'
              AND tc.table_name   = 'job_locks'
              AND tc.constraint_type = 'PRIMARY KEY'
            """
        )
        pk_cols = [row[0] for row in db_cursor.fetchall()]
        assert pk_cols == ["name"], (
            f"meta.job_locks primary key should be (name), got: {pk_cols}"
        )


class TestMetaRefreshStateSchema:
    """meta.refresh_state must have the columns required for resume tracking."""

    EXPECTED_COLUMNS = {
        "procedure_name",
        "last_chunk_position",
        "last_commit_at",
        "status",
    }

    def test_meta_refresh_state_schema(self, db_cursor):
        db_cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'meta'
              AND table_name   = 'refresh_state'
            """
        )
        actual = {row[0] for row in db_cursor.fetchall()}
        missing = self.EXPECTED_COLUMNS - actual
        assert not missing, (
            f"meta.refresh_state is missing columns: {missing}. "
            f"Existing columns: {actual}"
        )

    def test_meta_refresh_state_status_default(self, db_cursor):
        """The 'status' column should have a default of 'in_progress'."""
        db_cursor.execute(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = 'meta'
              AND table_name   = 'refresh_state'
              AND column_name  = 'status'
            """
        )
        row = db_cursor.fetchone()
        assert row is not None, "meta.refresh_state.status column not found"
        assert row[0] is not None, "meta.refresh_state.status has no default"
        assert "in_progress" in str(row[0]), (
            f"Expected default 'in_progress' in status column default, got: {row[0]}"
        )


class TestMetaTransformRunsSchema:
    """meta.transform_runs must have the WAL accounting columns."""

    EXPECTED_COLUMNS = {
        "run_id",
        "procedure_name",
        "chunk_position",
        "started_at",
        "ended_at",
        "rows_processed",
        "wal_bytes",
    }

    def test_meta_transform_runs_schema(self, db_cursor):
        db_cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'meta'
              AND table_name   = 'transform_runs'
            """
        )
        actual = {row[0] for row in db_cursor.fetchall()}
        missing = self.EXPECTED_COLUMNS - actual
        assert not missing, (
            f"meta.transform_runs is missing columns: {missing}. "
            f"Existing columns: {actual}"
        )


def test_verify_bootstrap_order():
    """
    >>> # Bootstrap execution order (smallest/least-dependent first):
    >>> # Tier 0: facilities (6K), companies (10K), conditions (50K)
    >>> # Tier 1: targets (500K), molecules (500K), designs (3M), drug_products
    >>> # Tier 2: trademarks (12M), patents (5M)
    >>> # Last: providers (10M — LARGEST, no dependencies)
    >>> # Post-hub: researchers (2M — depends on nothing in silver hubs)
    >>> # Final: researcher_provider_crosswalk (depends on providers + researchers)
    >>> schemas_and_procs = [p[0] + '.' + p[1] for p in [
    ...     ("hcs_silver", "bootstrap_facilities"),
    ...     ("mol_silver", "bootstrap_companies"),
    ...     ("ind_silver", "bootstrap_conditions"),
    ...     ("mol_silver", "bootstrap_targets"),
    ...     ("mol_silver", "bootstrap_molecules"),
    ...     ("ip_silver",  "bootstrap_designs"),
    ...     ("mol_silver", "bootstrap_drug_products"),
    ...     ("ip_silver",  "bootstrap_trademarks"),
    ...     ("ip_silver",  "bootstrap_patents"),
    ...     ("hcs_silver", "bootstrap_providers"),
    ...     ("hcp_silver", "bootstrap_researchers"),
    ...     ("hcp_silver", "bootstrap_researcher_provider_crosswalk"),
    ... ]]
    >>> len(schemas_and_procs)
    12
    >>> schemas_and_procs[0]
    'hcs_silver.bootstrap_facilities'
    >>> schemas_and_procs[-1]
    'hcp_silver.bootstrap_researcher_provider_crosswalk'
    """
    # Crosswalk must be LAST (depends on both providers and researchers)
    last_two = [p[0] + "." + p[1] for p in BOOTSTRAP_PROCEDURES[-2:]]
    assert "hcp_silver.bootstrap_researchers" in last_two
    assert "hcp_silver.bootstrap_researcher_provider_crosswalk" == last_two[-1]

    # Providers (LARGEST) must come before crosswalk
    proc_names = [p[1] for p in BOOTSTRAP_PROCEDURES]
    providers_idx = proc_names.index("bootstrap_providers")
    researchers_idx = proc_names.index("bootstrap_researchers")
    crosswalk_idx = proc_names.index("bootstrap_researcher_provider_crosswalk")

    assert providers_idx < crosswalk_idx, "bootstrap_providers must run before crosswalk"
    assert researchers_idx < crosswalk_idx, "bootstrap_researchers must run before crosswalk"
