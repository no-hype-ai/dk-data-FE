"""
T062: Unit tests for the remaining 8 resolve functions:
  - mol_silver.resolve_target
  - ind_silver.resolve_condition
  - mol_silver.resolve_company
  - hcs_silver.resolve_provider
  - hcs_silver.resolve_facility
  - hcp_silver.resolve_researcher
  - ip_silver.resolve_patent
  - ip_silver.resolve_trademark
  - ip_silver.resolve_design

Each entity has at least 2 tests: exact-match hit and NULL-on-no-match.
Integration tests only — require a real Postgres instance with the resolve
functions installed via the 006–014 migrations.

Fuzzy tests are skipped when pg_trgm is not available.
"""
import os
import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _check_trgm(cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm';")
    count = cur.fetchone()[0]
    cur.close()
    return count > 0


def _run_sql_file(cnpg_conn, filename):
    sql_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        f"../src/dk_data/sql/migrations/{filename}"
    ))
    with open(sql_path) as fh:
        sql = fh.read()
    cur = cnpg_conn.cursor()
    cur.execute(sql)
    cnpg_conn.commit()
    cur.close()


# ===========================================================================
# TARGET
# ===========================================================================

@pytest.fixture(scope="session")
def target_schema(cnpg_meta_schemas, cnpg_conn):
    """Create minimal mol_silver target tables."""
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS mol_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.targets (
            target_id      bigserial PRIMARY KEY,
            uniprot_id     text UNIQUE,
            sequence_hash  text UNIQUE,
            created_at     timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.target_identifiers (
            id          bigserial PRIMARY KEY,
            source      text   NOT NULL,
            identifier  text   NOT NULL,
            target_id   bigint NOT NULL REFERENCES mol_silver.targets(target_id) ON DELETE CASCADE,
            is_primary  boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tgt_ident_src_id
            ON mol_silver.target_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.target_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            target_id       bigint NOT NULL REFERENCES mol_silver.targets(target_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, target_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tgt_names_norm
            ON mol_silver.target_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "180_resolve_target.sql")
    yield


@pytest.fixture
def target_seed(target_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO mol_silver.targets (uniprot_id, sequence_hash)
        VALUES ('P00533', 'seqhash_egfr_test')
        ON CONFLICT (uniprot_id) DO UPDATE SET sequence_hash = EXCLUDED.sequence_hash
        RETURNING target_id;
    """)
    tid = cur.fetchone()[0]
    idents = [
        ('uniprot',        'P00533'),
        ('chembl_target',  'CHEMBL203'),
        ('gene_symbol',    'EGFR'),
        ('entrez',         '1956'),
        ('ensembl',        'ENSG00000146648'),
        ('pdb',            '1IVO'),
    ]
    for src, ident in idents:
        cur.execute("""
            INSERT INTO mol_silver.target_identifiers (source, identifier, target_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (src, ident, tid))
    cur.execute("""
        INSERT INTO mol_silver.target_names (normalized_name, target_id, name_kind, source, display_name)
        VALUES ('epidermal growth factor receptor', %s, 'protein_name', 'uniprot', 'EGFR')
        ON CONFLICT (normalized_name, target_id, source) DO NOTHING;
    """, (tid,))
    cnpg_conn.commit()
    yield tid
    cur.execute("DELETE FROM mol_silver.target_names WHERE target_id = %s;", (tid,))
    cur.execute("DELETE FROM mol_silver.target_identifiers WHERE target_id = %s;", (tid,))
    cur.execute("DELETE FROM mol_silver.targets WHERE target_id = %s;", (tid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveTarget:
    def test_resolves_by_uniprot(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target(p_uniprot_id => %s);", ('P00533',))
        assert cur.fetchone()[0] == target_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_chembl_target(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target(p_chembl_target_id => %s);", ('CHEMBL203',))
        assert cur.fetchone()[0] == target_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_gene_symbol(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target(p_gene_symbol => %s);", ('EGFR',))
        assert cur.fetchone()[0] == target_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_sequence_hash(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target(p_sequence_hash => %s);", ('seqhash_egfr_test',))
        assert cur.fetchone()[0] == target_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_returns_null(self, cnpg_conn, target_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_target(p_uniprot_id => %s);", ('X99999',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# CONDITION
# ===========================================================================

@pytest.fixture(scope="session")
def condition_schema(cnpg_meta_schemas, cnpg_conn):
    """Create minimal ind_silver condition tables."""
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ind_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ind_silver.conditions (
            condition_id        bigserial PRIMARY KEY,
            icd11_code          text UNIQUE,
            icd10_code          text,
            mesh_descriptor_id  text UNIQUE,
            meddra_pt           text,
            created_at          timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ind_silver.condition_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            condition_id    bigint NOT NULL REFERENCES ind_silver.conditions(condition_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, condition_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cond_names_norm
            ON ind_silver.condition_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "181_resolve_condition.sql")
    yield


@pytest.fixture
def condition_seed(condition_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO ind_silver.conditions
            (icd11_code, icd10_code, mesh_descriptor_id, meddra_pt)
        VALUES ('6A80', 'F32.9', 'D003865', 'Major depressive disorder')
        ON CONFLICT (icd11_code) DO UPDATE SET icd10_code = EXCLUDED.icd10_code
        RETURNING condition_id;
    """)
    cid = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO ind_silver.condition_names
            (normalized_name, condition_id, name_kind, source, display_name)
        VALUES ('major depressive disorder', %s, 'preferred', 'mesh', 'Major Depressive Disorder')
        ON CONFLICT (normalized_name, condition_id, source) DO NOTHING;
    """, (cid,))
    cnpg_conn.commit()
    yield cid
    cur.execute("DELETE FROM ind_silver.condition_names WHERE condition_id = %s;", (cid,))
    cur.execute("DELETE FROM ind_silver.conditions WHERE condition_id = %s;", (cid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveCondition:
    def test_resolves_by_icd11(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition(p_icd11 => %s);", ('6A80',))
        assert cur.fetchone()[0] == condition_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_icd10(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition(p_icd10 => %s);", ('F32.9',))
        assert cur.fetchone()[0] == condition_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_mesh(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition(p_mesh => %s);", ('D003865',))
        assert cur.fetchone()[0] == condition_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_meddra_pt(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition(p_meddra_pt => %s);",
                    ('Major depressive disorder',))
        assert cur.fetchone()[0] == condition_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_returns_null(self, cnpg_conn, condition_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ind_silver.resolve_condition(p_icd11 => %s);", ('ZZZ.999',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# COMPANY
# ===========================================================================

@pytest.fixture(scope="session")
def company_schema(cnpg_meta_schemas, cnpg_conn):
    """Create minimal mol_silver company tables."""
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS mol_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.companies (
            company_id  bigserial PRIMARY KEY,
            cik         text UNIQUE,
            ticker      text,
            created_at  timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.company_identifiers (
            id          bigserial PRIMARY KEY,
            source      text   NOT NULL,
            identifier  text   NOT NULL,
            company_id  bigint NOT NULL REFERENCES mol_silver.companies(company_id) ON DELETE CASCADE,
            is_primary  boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_co_ident_src_id
            ON mol_silver.company_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mol_silver.company_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            company_id      bigint NOT NULL REFERENCES mol_silver.companies(company_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, company_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_co_names_norm
            ON mol_silver.company_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "182_resolve_company.sql")
    yield


@pytest.fixture
def company_seed(company_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO mol_silver.companies (cik, ticker)
        VALUES ('0000078003', 'PFE')
        ON CONFLICT (cik) DO UPDATE SET ticker = EXCLUDED.ticker
        RETURNING company_id;
    """)
    coid = cur.fetchone()[0]
    for src, ident in [('cik', '0000078003'), ('ticker', 'PFE')]:
        cur.execute("""
            INSERT INTO mol_silver.company_identifiers (source, identifier, company_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (src, ident, coid))
    for norm, kind, display in [
        ('pfizer', 'normalized', 'Pfizer'),
        ('pfizer inc', 'with_suffix', 'Pfizer Inc.'),
    ]:
        cur.execute("""
            INSERT INTO mol_silver.company_names (normalized_name, company_id, name_kind, source, display_name)
            VALUES (%s, %s, %s, 'sec_edgar', %s)
            ON CONFLICT (normalized_name, company_id, source) DO NOTHING;
        """, (norm, coid, kind, display))
    cnpg_conn.commit()
    yield coid
    cur.execute("DELETE FROM mol_silver.company_names WHERE company_id = %s;", (coid,))
    cur.execute("DELETE FROM mol_silver.company_identifiers WHERE company_id = %s;", (coid,))
    cur.execute("DELETE FROM mol_silver.companies WHERE company_id = %s;", (coid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveCompany:
    def test_resolves_by_cik(self, cnpg_conn, company_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_company(p_cik => %s);", ('0000078003',))
        assert cur.fetchone()[0] == company_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_ticker(self, cnpg_conn, company_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_company(p_ticker => %s);", ('PFE',))
        assert cur.fetchone()[0] == company_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_name_with_suffix_stripped(self, cnpg_conn, company_seed):
        """'Pfizer Inc.' must match 'pfizer' after suffix stripping."""
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_company(p_name => %s);", ('Pfizer Inc.',))
        result = cur.fetchone()[0]
        cnpg_conn.rollback()
        cur.close()
        assert result == company_seed

    def test_null_returns_null(self, cnpg_conn, company_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_company();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_cik_returns_null(self, cnpg_conn, company_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT mol_silver.resolve_company(p_cik => %s);", ('9999999999',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# PROVIDER
# ===========================================================================

@pytest.fixture(scope="session")
def provider_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS hcs_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.providers (
            provider_id  bigserial PRIMARY KEY,
            npi          text UNIQUE,
            pecos_id     text,
            last_name    text,
            first_name   text,
            state        text,
            taxonomy     text,
            created_at   timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.provider_identifiers (
            id           bigserial PRIMARY KEY,
            source       text   NOT NULL,
            identifier   text   NOT NULL,
            provider_id  bigint NOT NULL REFERENCES hcs_silver.providers(provider_id) ON DELETE CASCADE,
            is_primary   boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_prov_ident_src_id
            ON hcs_silver.provider_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.provider_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            provider_id     bigint NOT NULL REFERENCES hcs_silver.providers(provider_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, provider_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_prov_names_norm
            ON hcs_silver.provider_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "183_resolve_provider.sql")
    yield


@pytest.fixture
def provider_seed(provider_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO hcs_silver.providers
            (npi, pecos_id, last_name, first_name, state, taxonomy)
        VALUES ('1234567890', 'PECOS12345', 'Smith', 'John', 'CA', '207Q00000X')
        ON CONFLICT (npi) DO UPDATE SET pecos_id = EXCLUDED.pecos_id
        RETURNING provider_id;
    """)
    pid = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO hcs_silver.provider_identifiers (source, identifier, provider_id)
        VALUES ('pecos', 'PECOS12345', %s)
        ON CONFLICT (source, identifier) DO NOTHING;
    """, (pid,))
    cur.execute("""
        INSERT INTO hcs_silver.provider_names
            (normalized_name, provider_id, name_kind, source, display_name)
        VALUES ('smith, john', %s, 'full_name', 'cms_nppes', 'Smith, John')
        ON CONFLICT (normalized_name, provider_id, source) DO NOTHING;
    """, (pid,))
    cnpg_conn.commit()
    yield pid
    cur.execute("DELETE FROM hcs_silver.provider_names WHERE provider_id = %s;", (pid,))
    cur.execute("DELETE FROM hcs_silver.provider_identifiers WHERE provider_id = %s;", (pid,))
    cur.execute("DELETE FROM hcs_silver.providers WHERE provider_id = %s;", (pid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveProvider:
    def test_resolves_by_npi(self, cnpg_conn, provider_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_provider(p_npi => %s);", ('1234567890',))
        assert cur.fetchone()[0] == provider_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_pecos_id(self, cnpg_conn, provider_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_provider(p_pecos_id => %s);", ('PECOS12345',))
        assert cur.fetchone()[0] == provider_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_name_state_taxonomy(self, cnpg_conn, provider_seed):
        """Composite name+state+taxonomy fuzzy must return provider when trgm available."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm not available")
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT hcs_silver.resolve_provider(
                p_first_name => 'John',
                p_last_name  => 'Smith',
                p_state      => 'CA',
                p_taxonomy   => '207Q00000X'
            );
        """)
        assert cur.fetchone()[0] == provider_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, provider_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_provider();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_npi_returns_null(self, cnpg_conn, provider_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_provider(p_npi => %s);", ('0000000000',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# FACILITY
# ===========================================================================

@pytest.fixture(scope="session")
def facility_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS hcs_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.facilities (
            facility_id     bigserial PRIMARY KEY,
            ccn             text UNIQUE,
            npi_type2       text UNIQUE,
            facility_name   text,
            city            text,
            state           text,
            zip             text,
            ownership_type  text,
            created_at      timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.facility_identifiers (
            id           bigserial PRIMARY KEY,
            source       text   NOT NULL,
            identifier   text   NOT NULL,
            facility_id  bigint NOT NULL REFERENCES hcs_silver.facilities(facility_id) ON DELETE CASCADE,
            is_primary   boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fac_ident_src_id
            ON hcs_silver.facility_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcs_silver.facility_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            facility_id     bigint NOT NULL REFERENCES hcs_silver.facilities(facility_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, facility_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_fac_names_norm
            ON hcs_silver.facility_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "184_resolve_facility.sql")
    yield


@pytest.fixture
def facility_seed(facility_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO hcs_silver.facilities
            (ccn, npi_type2, facility_name, city, state, zip)
        VALUES ('050246', '1427013906', 'General Test Hospital', 'Springfield', 'IL', '62701')
        ON CONFLICT (ccn) DO UPDATE SET npi_type2 = EXCLUDED.npi_type2
        RETURNING facility_id;
    """)
    fid = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO hcs_silver.facility_identifiers (source, identifier, facility_id)
        VALUES ('ncdr', 'NCDR12345TEST', %s)
        ON CONFLICT (source, identifier) DO NOTHING;
    """, (fid,))
    cur.execute("""
        INSERT INTO hcs_silver.facility_names
            (normalized_name, facility_id, name_kind, source, display_name)
        VALUES ('general test hospital', %s, 'legal', 'cms_nppes', 'General Test Hospital')
        ON CONFLICT (normalized_name, facility_id, source) DO NOTHING;
    """, (fid,))
    cnpg_conn.commit()
    yield fid
    cur.execute("DELETE FROM hcs_silver.facility_names WHERE facility_id = %s;", (fid,))
    cur.execute("DELETE FROM hcs_silver.facility_identifiers WHERE facility_id = %s;", (fid,))
    cur.execute("DELETE FROM hcs_silver.facilities WHERE facility_id = %s;", (fid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveFacility:
    def test_resolves_by_ccn(self, cnpg_conn, facility_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_facility(p_ccn => %s);", ('050246',))
        assert cur.fetchone()[0] == facility_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_npi_type2(self, cnpg_conn, facility_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_facility(p_npi_type2 => %s);", ('1427013906',))
        assert cur.fetchone()[0] == facility_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_ncdr_id(self, cnpg_conn, facility_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_facility(p_ncdr_id => %s);", ('NCDR12345TEST',))
        assert cur.fetchone()[0] == facility_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_name_city_state(self, cnpg_conn, facility_seed):
        """Name + city + state fuzzy must resolve when pg_trgm available."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm not available")
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT hcs_silver.resolve_facility(
                p_facility_name => 'General Test Hospital',
                p_city          => 'Springfield',
                p_state         => 'IL'
            );
        """)
        assert cur.fetchone()[0] == facility_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, facility_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_facility();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_ccn_returns_null(self, cnpg_conn, facility_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcs_silver.resolve_facility(p_ccn => %s);", ('000000',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# RESEARCHER
# ===========================================================================

@pytest.fixture(scope="session")
def researcher_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS hcp_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcp_silver.researchers (
            researcher_id                   bigserial PRIMARY KEY,
            orcid_id                        text UNIQUE,
            scopus_author_id                text,
            pubmed_author_signature         text UNIQUE,
            canonical_full_name             text,
            primary_affiliation_institution text,
            created_at                      timestamptz DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcp_silver.researcher_identifiers (
            id              bigserial PRIMARY KEY,
            source          text   NOT NULL,
            identifier      text   NOT NULL,
            researcher_id   bigint NOT NULL REFERENCES hcp_silver.researchers(researcher_id) ON DELETE CASCADE,
            is_primary      boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_res_ident_src_id
            ON hcp_silver.researcher_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hcp_silver.researcher_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            researcher_id   bigint NOT NULL REFERENCES hcp_silver.researchers(researcher_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, researcher_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_res_names_norm
            ON hcp_silver.researcher_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "185_resolve_researcher.sql")
    yield


@pytest.fixture
def researcher_seed(researcher_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO hcp_silver.researchers
            (orcid_id, scopus_author_id, pubmed_author_signature,
             canonical_full_name, primary_affiliation_institution)
        VALUES ('0000-0002-1825-0097', '57205473459', 'doe_j',
                'Doe, Jane', 'MIT')
        ON CONFLICT (orcid_id) DO UPDATE SET scopus_author_id = EXCLUDED.scopus_author_id
        RETURNING researcher_id;
    """)
    rid = cur.fetchone()[0]
    for src, ident in [
        ('orcid',         '0000-0002-1825-0097'),
        ('scopus_author', '57205473459'),
        ('researchgate',  'Jane_Doe99'),
        ('google_scholar','ABCDE12345'),
    ]:
        cur.execute("""
            INSERT INTO hcp_silver.researcher_identifiers (source, identifier, researcher_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (src, ident, rid))
    cur.execute("""
        INSERT INTO hcp_silver.researcher_names
            (normalized_name, researcher_id, name_kind, source, display_name)
        VALUES ('doe, jane', %s, 'full_name', 'openalex', 'Doe, Jane')
        ON CONFLICT (normalized_name, researcher_id, source) DO NOTHING;
    """, (rid,))
    cnpg_conn.commit()
    yield rid
    cur.execute("DELETE FROM hcp_silver.researcher_names WHERE researcher_id = %s;", (rid,))
    cur.execute("DELETE FROM hcp_silver.researcher_identifiers WHERE researcher_id = %s;", (rid,))
    cur.execute("DELETE FROM hcp_silver.researchers WHERE researcher_id = %s;", (rid,))
    cnpg_conn.commit()
    cur.close()


class TestResolveResearcher:
    def test_resolves_by_orcid(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher(p_orcid => %s);",
                    ('0000-0002-1825-0097',))
        assert cur.fetchone()[0] == researcher_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_scopus_author_id(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher(p_scopus_author_id => %s);",
                    ('57205473459',))
        assert cur.fetchone()[0] == researcher_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_pubmed_signature(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher(p_pubmed_signature => %s);",
                    ('doe_j',))
        assert cur.fetchone()[0] == researcher_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_researchgate_id(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher(p_researchgate_id => %s);",
                    ('Jane_Doe99',))
        assert cur.fetchone()[0] == researcher_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_orcid_returns_null(self, cnpg_conn, researcher_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT hcp_silver.resolve_researcher(p_orcid => %s);",
                    ('0000-0000-0000-0000',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# PATENT
# ===========================================================================

@pytest.fixture(scope="session")
def patent_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ip_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.patents (
            patent_id          bigserial PRIMARY KEY,
            jurisdiction       text NOT NULL,
            patent_number      text,
            application_number text,
            title              text,
            first_assignee     text,
            filing_date        date,
            grant_date         date,
            expiry_date        date,
            UNIQUE (jurisdiction, patent_number),
            UNIQUE (jurisdiction, application_number)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.patent_identifiers (
            id          bigserial PRIMARY KEY,
            source      text   NOT NULL,
            identifier  text   NOT NULL,
            patent_id   bigint NOT NULL REFERENCES ip_silver.patents(patent_id) ON DELETE CASCADE,
            is_primary  boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pat_ident_src_id
            ON ip_silver.patent_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.patent_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            patent_id       bigint NOT NULL REFERENCES ip_silver.patents(patent_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, patent_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_pat_names_norm
            ON ip_silver.patent_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "186_resolve_patent.sql")
    yield


@pytest.fixture
def patent_seed(patent_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO ip_silver.patents
            (jurisdiction, patent_number, application_number, title,
             first_assignee, filing_date, grant_date)
        VALUES
            ('US', 'US10123456B2', 'US16000001', 'Method for testing resolve functions',
             'Test Corp', '2018-01-15', '2021-06-01')
        ON CONFLICT (jurisdiction, patent_number) DO UPDATE
            SET application_number = EXCLUDED.application_number
        RETURNING patent_id;
    """)
    pat_id = cur.fetchone()[0]
    for src, ident in [
        ('publication_number', 'US20190123456A1'),
        ('pct_application',    'PCT/US2018/000001'),
    ]:
        cur.execute("""
            INSERT INTO ip_silver.patent_identifiers (source, identifier, patent_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (source, identifier) DO NOTHING;
        """, (src, ident, pat_id))
    cur.execute("""
        INSERT INTO ip_silver.patent_names
            (normalized_name, patent_id, name_kind, source, display_name)
        VALUES ('method for testing resolve functions', %s, 'title', 'uspto_patents',
                'Method for testing resolve functions')
        ON CONFLICT (normalized_name, patent_id, source) DO NOTHING;
    """, (pat_id,))
    cnpg_conn.commit()
    yield pat_id
    cur.execute("DELETE FROM ip_silver.patent_names WHERE patent_id = %s;", (pat_id,))
    cur.execute("DELETE FROM ip_silver.patent_identifiers WHERE patent_id = %s;", (pat_id,))
    cur.execute("DELETE FROM ip_silver.patents WHERE patent_id = %s;", (pat_id,))
    cnpg_conn.commit()
    cur.close()


class TestResolvePatent:
    def test_resolves_by_jurisdiction_and_patent_number(self, cnpg_conn, patent_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_patent(
                p_jurisdiction  => 'US',
                p_patent_number => 'US10123456B2'
            );
        """)
        assert cur.fetchone()[0] == patent_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_jurisdiction_and_application_number(self, cnpg_conn, patent_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_patent(
                p_jurisdiction       => 'US',
                p_application_number => 'US16000001'
            );
        """)
        assert cur.fetchone()[0] == patent_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_pct_application(self, cnpg_conn, patent_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_patent(p_pct_application => %s);
        """, ('PCT/US2018/000001',))
        assert cur.fetchone()[0] == patent_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, patent_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ip_silver.resolve_patent();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_wrong_jurisdiction_returns_null(self, cnpg_conn, patent_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_patent(
                p_jurisdiction  => 'EP',
                p_patent_number => 'US10123456B2'
            );
        """)
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# TRADEMARK
# ===========================================================================

@pytest.fixture(scope="session")
def trademark_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ip_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.trademarks (
            trademark_id         bigserial PRIMARY KEY,
            jurisdiction         text NOT NULL,
            registration_number  text,
            serial_number        text,
            mark_text            text,
            nice_classes         int[],
            created_at           timestamptz DEFAULT NOW(),
            UNIQUE (jurisdiction, registration_number)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.trademark_identifiers (
            id            bigserial PRIMARY KEY,
            source        text   NOT NULL,
            identifier    text   NOT NULL,
            trademark_id  bigint NOT NULL REFERENCES ip_silver.trademarks(trademark_id) ON DELETE CASCADE,
            is_primary    boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tm_ident_src_id
            ON ip_silver.trademark_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.trademark_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            trademark_id    bigint NOT NULL REFERENCES ip_silver.trademarks(trademark_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, trademark_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tm_names_norm
            ON ip_silver.trademark_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "187_resolve_trademark.sql")
    yield


@pytest.fixture
def trademark_seed(trademark_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO ip_silver.trademarks
            (jurisdiction, registration_number, serial_number, mark_text, nice_classes)
        VALUES ('US', 'US5123456', '87654321', 'TESTMARK PRO', ARRAY[5, 10, 42])
        ON CONFLICT (jurisdiction, registration_number) DO UPDATE
            SET serial_number = EXCLUDED.serial_number
        RETURNING trademark_id;
    """)
    tm_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO ip_silver.trademark_identifiers (source, identifier, trademark_id)
        VALUES ('wipo_madrid', 'MM123456', %s)
        ON CONFLICT (source, identifier) DO NOTHING;
    """, (tm_id,))
    cur.execute("""
        INSERT INTO ip_silver.trademark_names
            (normalized_name, trademark_id, name_kind, source, display_name)
        VALUES ('testmark pro', %s, 'mark_text', 'uspto', 'TESTMARK PRO')
        ON CONFLICT (normalized_name, trademark_id, source) DO NOTHING;
    """, (tm_id,))
    cnpg_conn.commit()
    yield tm_id
    cur.execute("DELETE FROM ip_silver.trademark_names WHERE trademark_id = %s;", (tm_id,))
    cur.execute("DELETE FROM ip_silver.trademark_identifiers WHERE trademark_id = %s;", (tm_id,))
    cur.execute("DELETE FROM ip_silver.trademarks WHERE trademark_id = %s;", (tm_id,))
    cnpg_conn.commit()
    cur.close()


class TestResolveTrademark:
    def test_resolves_by_jurisdiction_and_registration_number(self, cnpg_conn, trademark_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_trademark(
                p_jurisdiction        => 'US',
                p_registration_number => 'US5123456'
            );
        """)
        assert cur.fetchone()[0] == trademark_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_wipo_madrid(self, cnpg_conn, trademark_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_trademark(p_wipo_madrid_number => %s);
        """, ('MM123456',))
        assert cur.fetchone()[0] == trademark_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_mark_text_fuzzy(self, cnpg_conn, trademark_seed):
        """Exact mark text must resolve via fuzzy fallback (similarity=1.0)."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm not available")
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_trademark(p_mark_text => %s);
        """, ('testmark pro',))
        assert cur.fetchone()[0] == trademark_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, trademark_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ip_silver.resolve_trademark();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_wrong_registration_number_returns_null(self, cnpg_conn, trademark_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_trademark(
                p_jurisdiction        => 'US',
                p_registration_number => 'XXXXXXXXX'
            );
        """)
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()


# ===========================================================================
# DESIGN
# ===========================================================================

@pytest.fixture(scope="session")
def design_schema(cnpg_meta_schemas, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS ip_silver;")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.designs (
            design_id       bigserial PRIMARY KEY,
            jurisdiction    text NOT NULL,
            design_number   text NOT NULL,
            locarno_classes int[],
            filing_date     date,
            created_at      timestamptz DEFAULT NOW(),
            UNIQUE (jurisdiction, design_number)
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.design_identifiers (
            id          bigserial PRIMARY KEY,
            source      text   NOT NULL,
            identifier  text   NOT NULL,
            design_id   bigint NOT NULL REFERENCES ip_silver.designs(design_id) ON DELETE CASCADE,
            is_primary  boolean DEFAULT false,
            UNIQUE (source, identifier)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_des_ident_src_id
            ON ip_silver.design_identifiers (source, identifier);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ip_silver.design_names (
            id              bigserial PRIMARY KEY,
            normalized_name text   NOT NULL,
            design_id       bigint NOT NULL REFERENCES ip_silver.designs(design_id) ON DELETE CASCADE,
            name_kind       text,
            source          text,
            display_name    text,
            UNIQUE (normalized_name, design_id, source)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_des_names_norm
            ON ip_silver.design_names (normalized_name);
    """)
    cnpg_conn.commit()
    cur.close()
    _run_sql_file(cnpg_conn, "188_resolve_design.sql")
    yield


@pytest.fixture
def design_seed(design_schema, cnpg_conn):
    cur = cnpg_conn.cursor()
    cur.execute("""
        INSERT INTO ip_silver.designs
            (jurisdiction, design_number, locarno_classes, filing_date)
        VALUES ('EUIPO', 'DES001234567', ARRAY[14, 19], '2020-03-10')
        ON CONFLICT (jurisdiction, design_number) DO UPDATE
            SET locarno_classes = EXCLUDED.locarno_classes
        RETURNING design_id;
    """)
    did = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO ip_silver.design_identifiers (source, identifier, design_id)
        VALUES ('wipo_hague', 'DM/099999', %s)
        ON CONFLICT (source, identifier) DO NOTHING;
    """, (did,))
    cur.execute("""
        INSERT INTO ip_silver.design_names
            (normalized_name, design_id, name_kind, source, display_name)
        VALUES ('test design holder corp', %s, 'holder', 'euipo', 'Test Design Holder Corp')
        ON CONFLICT (normalized_name, design_id, source) DO NOTHING;
    """, (did,))
    cnpg_conn.commit()
    yield did
    cur.execute("DELETE FROM ip_silver.design_names WHERE design_id = %s;", (did,))
    cur.execute("DELETE FROM ip_silver.design_identifiers WHERE design_id = %s;", (did,))
    cur.execute("DELETE FROM ip_silver.designs WHERE design_id = %s;", (did,))
    cnpg_conn.commit()
    cur.close()


class TestResolveDesign:
    def test_resolves_by_jurisdiction_and_design_number(self, cnpg_conn, design_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_design(
                p_jurisdiction  => 'EUIPO',
                p_design_number => 'DES001234567'
            );
        """)
        assert cur.fetchone()[0] == design_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_wipo_hague(self, cnpg_conn, design_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_design(p_wipo_hague_number => %s);
        """, ('DM/099999',))
        assert cur.fetchone()[0] == design_seed
        cnpg_conn.rollback()
        cur.close()

    def test_resolves_by_holder_fuzzy(self, cnpg_conn, design_seed):
        """Exact holder name must resolve via fuzzy fallback when pg_trgm available."""
        if not _check_trgm(cnpg_conn):
            pytest.skip("pg_trgm not available")
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_design(p_holder => %s);
        """, ('test design holder corp',))
        assert cur.fetchone()[0] == design_seed
        cnpg_conn.rollback()
        cur.close()

    def test_null_returns_null(self, cnpg_conn, design_seed):
        cur = cnpg_conn.cursor()
        cur.execute("SELECT ip_silver.resolve_design();")
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_wrong_jurisdiction_returns_null(self, cnpg_conn, design_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_design(
                p_jurisdiction  => 'USPTO',
                p_design_number => 'DES001234567'
            );
        """)
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()

    def test_unknown_wipo_returns_null(self, cnpg_conn, design_seed):
        cur = cnpg_conn.cursor()
        cur.execute("""
            SELECT ip_silver.resolve_design(p_wipo_hague_number => %s);
        """, ('DM/XXXXXX',))
        assert cur.fetchone()[0] is None
        cnpg_conn.rollback()
        cur.close()
