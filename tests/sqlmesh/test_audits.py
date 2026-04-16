"""Integration test for SQLMesh audits at silver/gold layer boundaries (C.7).

Verifies that:

1. Custom audits in ``src/dk_data/sqlmesh/audits/custom_audits.sql`` load and parse.
2. The canonical silver hub ``mol_silver.molecules`` declares its audits.
3. Each declared audit renders to valid SQL and returns zero rows against a
   clean in-memory DuckDB fixture (PASS semantics in SQLMesh: empty result).
4. Mutating the fixture (null an ER key, duplicate the natural key, empty the
   table) causes the relevant audit to return ≥1 row (FAIL).

Runs hermetically — no Postgres required. DuckDB is used because SQLMesh's
audit rendering uses a dialect-portable subset of SQL (COUNT(*), ROW_NUMBER,
NOT EXISTS), and DuckDB accepts the Postgres-dialect rendered SQL via the
``sqlglot`` transpile performed by SQLMesh's renderer.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from sqlmesh.core import dialect as d
from sqlmesh.core.audit.builtin import BUILT_IN_AUDITS
from sqlmesh.core.audit.definition import load_multiple_audits
from sqlmesh.core.model import load_sql_based_model

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDITS_DIR = REPO_ROOT / "src" / "dk_data" / "sqlmesh" / "audits"
MODELS_DIR = REPO_ROOT / "src" / "dk_data" / "sqlmesh" / "models"


def _load_custom_audits() -> dict:
    """Parse every .sql file in audits/ and return {name: Audit}."""
    audits: dict = {}
    for path in sorted(AUDITS_DIR.glob("*.sql")):
        exprs = d.parse(path.read_text(), default_dialect="postgres")
        for audit in load_multiple_audits(
            expressions=exprs,
            path=path,
            module_path=REPO_ROOT / "src" / "dk_data" / "sqlmesh",
            macros={},
            jinja_macros=None,
            dialect="postgres",
            default_catalog=None,
            variables=None,
        ):
            audits[audit.name] = audit
    return audits


@pytest.fixture(scope="module")
def audit_defs() -> dict:
    """Built-in + custom audit registry."""
    return {**BUILT_IN_AUDITS, **_load_custom_audits()}


def _load_model(relative_path: str, audit_defs: dict):
    path = MODELS_DIR / relative_path
    exprs = d.parse(path.read_text(), default_dialect="postgres")
    return load_sql_based_model(exprs, audit_definitions=audit_defs, dialect="postgres")


@pytest.fixture
def duckdb_conn():
    """Fresh in-memory DuckDB with the mol_silver schema pre-created.

    SQLMesh renders fully-qualified names ("mol_silver"."molecules"); DuckDB
    supports schemas natively so the rendered SQL executes unmodified.
    """
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE SCHEMA IF NOT EXISTS mol_silver")
    yield conn
    conn.close()


def _seed_clean_molecules(conn) -> None:
    """Insert a minimal valid fixture — one row per unique molecule_id."""
    conn.execute("DROP TABLE IF EXISTS mol_silver.molecules")
    conn.execute(
        """
        CREATE TABLE mol_silver.molecules (
            molecule_id BIGINT,
            inchi_key TEXT,
            inchi TEXT,
            canonical_smiles TEXT,
            sequence_hash TEXT,
            is_biologic BOOLEAN,
            molecule_type TEXT,
            parent_molecule_id BIGINT,
            canonical_name TEXT,
            max_phase INTEGER,
            first_approval INTEGER,
            molecular_formula TEXT,
            molecular_weight DECIMAL,
            mechanism_of_action TEXT,
            therapeutic_areas TEXT[],
            first_seen_at TIMESTAMPTZ,
            last_updated_at TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        """
        INSERT INTO mol_silver.molecules (molecule_id, canonical_name, is_biologic)
        VALUES
          (1, 'Aspirin',      FALSE),
          (2, 'Ibuprofen',    FALSE),
          (3, 'Pembrolizumab', TRUE)
        """
    )


def _execute_audit(conn, model, audit, args) -> int:
    """Render the audit query and return the row count — zero = PASS."""
    rendered = model.render_audit_query(audit, **args)
    sql = rendered.sql(dialect="postgres")
    # DuckDB executes Postgres-dialect SQL for the subset used by built-in and
    # custom audits (COUNT, ROW_NUMBER, NOT EXISTS, IS NULL). We wrap in a
    # subquery the same way the evaluator does.
    return conn.execute(f"SELECT COUNT(*) FROM ({sql}) AS _audit").fetchone()[0]


# -------------------------------------------------------------------------
# 1. Structural: custom audits load
# -------------------------------------------------------------------------
def test_custom_audits_load():
    audits = _load_custom_audits()
    expected = {
        "referential_integrity",
        "freshness_threshold",
        "row_count_above",
        "row_count_within_pct",
    }
    assert expected <= set(audits), (
        f"Missing custom audits: {expected - set(audits)}"
    )


# -------------------------------------------------------------------------
# 2. Canonical silver hub declares its audits
# -------------------------------------------------------------------------
def test_molecules_hub_declares_audits(audit_defs):
    model = _load_model("molecules/silver/molecules.sql", audit_defs)
    audit_names = {audit.name for audit, _ in model.audits_with_args}
    assert "not_null" in audit_names, "mol_silver.molecules missing not_null audit"
    assert "unique_values" in audit_names, (
        "mol_silver.molecules missing unique_values audit"
    )


# -------------------------------------------------------------------------
# 3. PASS on clean fixture
# -------------------------------------------------------------------------
def test_audits_pass_on_clean_fixture(audit_defs, duckdb_conn):
    _seed_clean_molecules(duckdb_conn)
    model = _load_model("molecules/silver/molecules.sql", audit_defs)
    for audit, args in model.audits_with_args:
        count = _execute_audit(duckdb_conn, model, audit, args)
        assert count == 0, (
            f"Audit {audit.name} returned {count} rows on clean fixture — expected 0 (PASS)"
        )


# -------------------------------------------------------------------------
# 4a. FAIL when an ER key is NULL (not_null audit)
# -------------------------------------------------------------------------
def test_not_null_fails_when_hub_key_null(audit_defs, duckdb_conn):
    _seed_clean_molecules(duckdb_conn)
    # Null out the canonical_name — a declared not_null column
    duckdb_conn.execute(
        "UPDATE mol_silver.molecules SET canonical_name = NULL WHERE molecule_id = 1"
    )
    model = _load_model("molecules/silver/molecules.sql", audit_defs)
    not_null_audit = next(
        (a, args) for a, args in model.audits_with_args if a.name == "not_null"
    )
    count = _execute_audit(duckdb_conn, model, *not_null_audit)
    assert count >= 1, "not_null audit should FAIL (≥1 row) when canonical_name is NULL"


# -------------------------------------------------------------------------
# 4b. FAIL when natural key is duplicated (unique_values audit)
# -------------------------------------------------------------------------
def test_unique_values_fails_when_key_duplicated(audit_defs, duckdb_conn):
    _seed_clean_molecules(duckdb_conn)
    # Insert a row whose molecule_id collides with an existing row
    duckdb_conn.execute(
        """
        INSERT INTO mol_silver.molecules (molecule_id, canonical_name, is_biologic)
        VALUES (1, 'Duplicate-Aspirin', FALSE)
        """
    )
    model = _load_model("molecules/silver/molecules.sql", audit_defs)
    unique_audit = next(
        (a, args) for a, args in model.audits_with_args if a.name == "unique_values"
    )
    count = _execute_audit(duckdb_conn, model, *unique_audit)
    assert count >= 1, (
        "unique_values audit should FAIL (≥1 row) when molecule_id is duplicated"
    )


# -------------------------------------------------------------------------
# 5. Custom referential_integrity FAILs on orphan FK (via ip_silver.patents)
# -------------------------------------------------------------------------
def test_referential_integrity_fails_on_orphan_fk(audit_defs, duckdb_conn):
    # Seed hub with 1 row, then seed patents with molecule_id pointing to
    # a non-existent hub row.
    duckdb_conn.execute("DROP TABLE IF EXISTS mol_silver.molecules")
    duckdb_conn.execute(
        "CREATE TABLE mol_silver.molecules (molecule_id BIGINT, canonical_name TEXT)"
    )
    duckdb_conn.execute(
        "INSERT INTO mol_silver.molecules VALUES (42, 'LiveHub')"
    )

    duckdb_conn.execute("CREATE SCHEMA IF NOT EXISTS ip_silver")
    duckdb_conn.execute("DROP TABLE IF EXISTS ip_silver.patents")
    duckdb_conn.execute(
        "CREATE TABLE ip_silver.patents (patent_id BIGINT, jurisdiction TEXT, molecule_id BIGINT)"
    )
    duckdb_conn.execute(
        """
        INSERT INTO ip_silver.patents (patent_id, jurisdiction, molecule_id) VALUES
          (1, 'US', 42),  -- matches hub
          (2, 'US', 99),  -- orphan: hub has no molecule_id 99
          (3, 'EU', NULL) -- null FK: skipped by the audit
        """
    )

    model = _load_model("ip/silver/patents.sql", audit_defs)
    ri_audit = next(
        (a, args) for a, args in model.audits_with_args if a.name == "referential_integrity"
    )
    count = _execute_audit(duckdb_conn, model, *ri_audit)
    assert count == 1, (
        f"referential_integrity should FAIL on exactly 1 orphan FK; got {count}"
    )


# -------------------------------------------------------------------------
# 6. row_count_above FAILs when fixture is empty (silent-drop guard)
# -------------------------------------------------------------------------
def test_row_count_above_fails_on_empty_table(audit_defs, duckdb_conn):
    """The custom row_count_above audit catches the silent-drop failure class.

    We use the gold model that declares it (``mol_gold.molecule_profile``) and
    verify that rendering + executing it against an empty fixture returns a row.
    """
    duckdb_conn.execute("CREATE SCHEMA IF NOT EXISTS mol_gold")
    duckdb_conn.execute("DROP TABLE IF EXISTS mol_gold.molecule_profile")
    duckdb_conn.execute(
        "CREATE TABLE mol_gold.molecule_profile (molecule_id BIGINT, canonical_name TEXT, updated_at TIMESTAMPTZ)"
    )
    # Empty table — should fail any row_count_above(min_rows := N>0).

    model = _load_model("molecules/gold/molecule_profile.sql", audit_defs)
    rca = next(
        (a, args) for a, args in model.audits_with_args if a.name == "row_count_above"
    )
    count = _execute_audit(duckdb_conn, model, *rca)
    assert count == 1, (
        "row_count_above should FAIL on empty table (catches silent drop)"
    )
