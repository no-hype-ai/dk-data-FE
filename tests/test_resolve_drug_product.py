"""
T061: Unit tests for mol_silver.resolve_drug_product().

Integration tests against a real PostgreSQL instance (no mocks).

Setup: creates a minimal mol_silver schema subset for drug_products:
  - mol_silver.drug_products          (product_id, rxcui, bla_number, application_number,
                                        brand_name, generic_name, dosage_form, route,
                                        is_biologic, strength_mg)
  - mol_silver.drug_product_identifiers (source, identifier, product_id)
  - mol_silver.drug_product_names      (normalized_name, product_id, name_kind, source)

Key invariant: RxCUI IN/PIN/BN must return NULL — only SCD/SBD/GPCK/BPCK are valid.

Fuzzy tests are skipped when pg_trgm is not available.
"""
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_trgm(cnpg_conn):
    """Return True if pg_trgm extension is available in the test DB."""
    cur = cnpg_conn.cursor()
    cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm';")
    count = cur.fetchone()[0]
    cur.close()
    return count > 0


# ---------------------------------------------------------------------------
# Schema + function setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def drug_product_schema(cnpg_meta_schemas, cnpg_conn):
    """Create minimal drug product tables for resolve tests. Idempotent."""
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS mol_silver;")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.drug_products (
            product_id         bigserial PRIMARY KEY,
            rxcui              text UNIQUE,
            bla_number         text,
            application_number text,
            brand_name         text,
            generic_name       text,
            dosage_form        text,
            route              text,
            is_biologic        boolean DEFAULT false,
            strength_mg        numeric,
            last_updated_at    timestamptz DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.drug_product_identifiers (
            id          bigserial PRIMARY KEY,
            source      text   NOT NULL,
            identifier  text   NOT NULL,
            product_id  bigint NOT NULL REFERENCES mol_silver.drug_products(product_id) ON DELETE CASCADE,
            is_primary  boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_dp_ident_src_id
            ON mol_silver.drug_product_identifiers (source, identifier);
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.drug_product_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            product_id      bigint NOT NULL REFERENCES mol_silver.drug_products(product_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, product_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_dp_names_norm
            ON mol_silver.drug_product_names (normalized_name);
    """)

    cnpg_conn.commit()
    cur.close()
    yield


@pytest.fixture(scope="session")
def resolve_drug_product_fn(drug_product_schema, cnpg_conn):
    """Install resolve_drug_product into the test DB."""
    import os
    sql_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "../src/dk_data/sql/migrations/179_resolve_drug_product.sql"
    ))
    with open(sql_path) as fh:
        sql = fh.read()
    cur = cnpg_conn.cursor()
    cur.execute(sql)
    cnpg_conn.commit()
    cur.close()
    yield


@pytest.fixture
def drug_product_seed(drug_product_schema, resolve_drug_product_fn, cnpg_conn):
    """
    Insert one seed drug product (Humira biosimilar analog for testing) and
    return its product_id. Cleans up after each test.
    """
    cur = cnpg_conn.cursor()

    # Hub row — real-looking but test-only values
    cur.execute("""
        INSERT INTO mol_silver.drug_products
            (rxcui, bla_number, application_number, brand_name, generic_name,
             dosage_form, route, is_biologic, strength_mg)
        VALUES
            ('1872355', 'BLA125057', 'NDA021540',
             'Testbrand', 'adalimumab-test',
             'Prefilled Syringe', 'Subcutaneous', true, 40.0)
        ON CONFLICT (rxcui) DO UPDATE SET brand_name = EXCLUDED.brand_name
        RETURNING product_id;
    """)
    product_id = cur.fetchone()[0]

    # Identifiers
    idents = [
        ('ndc',            '00074-9374-01'),
        ('rxcui_scd_sbd',  '1872355'),
        ('ema_product',    'EMEA/H/C/000481'),
        ('cvx',            '998'),
        ('ingredients_hash', 'sha256:ada12345test'),
    ]
    for source, ident in idents:
        cur.execute("""
            INSERT INTO mol_silver.drug_product_identifiers (source, identifier, product_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (source, ident, product_id))

    # Names
    for norm, kind in [('testbrand', 'brand'), ('adalimumab-test', 'generic')]:
        cur.execute("""
            INSERT INTO mol_silver.drug_product_names
                (normalized_name, product_id, name_kind, source, display_name)
            VALUES (%s, %s, %s, 'test', %s)
            ON CONFLICT (normalized_name, product_id, source) DO NOTHING;
        """, (norm, product_id, kind, norm.title()))

    cnpg_conn.commit()
    yield product_id

    # Cleanup
    cur.execute("DELETE FROM mol_silver.drug_product_names WHERE product_id = %s;", (product_id,))
    cur.execute("DELETE FROM mol_silver.drug_product_identifiers WHERE product_id = %s;", (product_id,))
    cur.execute("DELETE FROM mol_silver.drug_products WHERE product_id = %s;", (product_id,))
    cnpg_conn.commit()
    cur.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResolveDrugProductExact:

    def test_resolves_by_ndc(self, cnpg_conn, drug_product_seed):
        """Tier 1: NDC lookup must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_ndc => %s);",
            ('00074-9374-01',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_rxcui_scd(self, cnpg_conn, drug_product_seed):
        """Tier 2: RxCUI SCD/SBD lookup must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_rxcui => %s);",
            ('1872355',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_bla_alone(self, cnpg_conn, drug_product_seed):
        """Tier 3 (BLA alone): BLA number alone must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_bla => %s);",
            ('BLA125057',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_application_number(self, cnpg_conn, drug_product_seed):
        """Tier 4: Application number alone must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_application_number => %s);",
            ('NDA021540',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_ema_product_number(self, cnpg_conn, drug_product_seed):
        """Tier 5: EMA product number must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_ema_product_number => %s);",
            ('EMEA/H/C/000481',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_cvx(self, cnpg_conn, drug_product_seed):
        """Tier 6: CVX vaccine code must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_cvx => %s);",
            ('998',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_resolves_by_ingredients_hash(self, cnpg_conn, drug_product_seed):
        """Tier 7: Ingredients hash must return the correct product_id."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_ingredients_hash => %s);",
            ('sha256:ada12345test',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed


class TestResolveDrugProductRxCUIGuard:
    """
    Verify that RxCUI IN/PIN/BN types stored under a different source key
    do NOT resolve through the SCD/SBD slot.
    """

    def test_rejects_rxcui_in_pin_bn(self, cnpg_conn, drug_product_schema,
                                      resolve_drug_product_fn):
        """
        An RxCUI stored under source='rxcui_in_pin' (molecule-tier) must NOT
        resolve via resolve_drug_product (which only queries 'rxcui_scd_sbd').

        This test creates an isolated product row and a conflicting 'rxcui_in_pin'
        identifier row to confirm the guard works.
        """
        cur = cnpg_conn.cursor()

        # Insert a product
        cur.execute("""
            INSERT INTO mol_silver.drug_products (brand_name, generic_name)
            VALUES ('InPinTestBrand', 'inpin-generic')
            RETURNING product_id;
        """)
        product_id = cur.fetchone()[0]

        # Deliberately store RxCUI under 'rxcui_in_pin' (NOT 'rxcui_scd_sbd')
        cur.execute("""
            INSERT INTO mol_silver.drug_product_identifiers (source, identifier, product_id)
            VALUES ('rxcui_in_pin', '99887766', %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (product_id,))
        cnpg_conn.commit()

        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_rxcui => %s);",
            ('99887766',)
        )
        result = cur.fetchone()[0]

        # Cleanup
        cur.execute("DELETE FROM mol_silver.drug_product_identifiers WHERE product_id = %s;",
                    (product_id,))
        cur.execute("DELETE FROM mol_silver.drug_products WHERE product_id = %s;",
                    (product_id,))
        cnpg_conn.commit()
        cur.close()

        assert result is None, (
            "RxCUI stored under 'rxcui_in_pin' must NOT be returned by "
            f"resolve_drug_product (which queries 'rxcui_scd_sbd'). Got {result}"
        )


class TestResolveDrugProductFuzzy:
    """Tier 10: pg_trgm fuzzy brand name fallback."""

    def test_fuzzy_brand_match(self, cnpg_conn, drug_product_seed):
        """Exact brand name 'testbrand' must match via fuzzy fallback (similarity=1.0)."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm extension not available in test DB")

        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_brand => %s);",
            ('testbrand',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == drug_product_seed

    def test_fuzzy_brand_no_match_below_threshold(self, cnpg_conn, drug_product_seed):
        """An unrelated brand name must return NULL."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm extension not available in test DB")

        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_brand => %s);",
            ('zzzzz_totally_unknown_brand_xyz',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result is None


class TestResolveDrugProductEdgeCases:

    def test_null_inputs_return_null(self, cnpg_conn, drug_product_seed):
        """All-NULL inputs must return NULL."""
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_drug_product();")
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result is None

    def test_unknown_ndc_returns_null(self, cnpg_conn, drug_product_seed):
        """An NDC not in the hub must return NULL."""
        cur = cnpg_conn.cursor()
        cur.execute(
            "SELECT mol_silver.resolve_drug_product(p_ndc => %s);",
            ('00000-0000-00',)
        )
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result is None
