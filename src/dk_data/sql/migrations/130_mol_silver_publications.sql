-- Migration 130: Create mol_silver.publications and mol_silver.molecule_publications
-- Date: 2026-03-23
--
-- mol_silver.publications is the canonical publication table populated by the
-- SQLMesh publications model (openalex + europepmc + cochrane + pubmed).
-- SQLMesh manages DML; this migration creates the DDL so PostgREST can serve
-- it immediately and so xenon agents can query it before the first SQLMesh run.
--
-- mol_silver.molecule_publications is a VIEW over mol_silver.publications
-- filtered to rows where molecule_id is not null. It gives xenon agents a
-- molecule-scoped entry point (/molecule_publications?molecule_id=eq.<uuid>).

-- ─── 1. mol_silver.publications ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mol_silver.publications (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    molecule_id             UUID REFERENCES mol_silver.molecules(molecule_id) ON DELETE SET NULL,

    -- Identifiers (match bronze/API naming)
    openalex_id             VARCHAR(100),
    doi                     VARCHAR(500),
    pmid                    VARCHAR(20),
    pmcid                   VARCHAR(20),
    mag_id                  VARCHAR(50),

    -- Content
    title                   TEXT NOT NULL,
    abstract                TEXT,

    -- Publication metadata
    work_type               VARCHAR(100),
    language                VARCHAR(10),
    publication_year        INTEGER,
    publication_date        DATE,
    journal_name            VARCHAR(500),
    journal_issn            VARCHAR(20),
    pdf_url                 TEXT,
    is_open_access          BOOLEAN,
    volume                  VARCHAR(20),
    issue                   VARCHAR(20),
    first_page              VARCHAR(20),
    last_page               VARCHAR(20),

    -- Authors
    authorships             JSONB,
    author_names            JSONB,
    first_author_name       TEXT,
    first_author_id         TEXT,
    first_author_institution TEXT,
    author_count            INTEGER,

    -- Concepts / topics
    concepts                JSONB,
    topics                  JSONB,
    keywords                JSONB,
    mesh_terms              JSONB,

    -- Metrics
    cited_by_count          INTEGER,
    citation_counts_by_year JSONB,

    -- Grants and references
    grants                  JSONB,
    referenced_works        JSONB,
    related_works           JSONB,

    -- Open access
    open_access_info        JSONB,
    best_oa_location        JSONB,

    -- Status flags
    is_retracted            BOOLEAN,
    is_paratext             BOOLEAN,

    -- Source tracking
    source                  VARCHAR(50),
    source_updated_at       TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(doi)
);

-- Indexes only if publications is a plain table (SQLMesh may have created it as a view)
DO $$ BEGIN
    IF (SELECT relkind FROM pg_class c JOIN pg_namespace n ON c.relnamespace=n.oid
        WHERE n.nspname='mol_silver' AND c.relname='publications') = 'r' THEN
        CREATE INDEX IF NOT EXISTS idx_mol_silver_pub_molecule_id ON mol_silver.publications(molecule_id);
        CREATE INDEX IF NOT EXISTS idx_mol_silver_pub_doi         ON mol_silver.publications(doi);
        CREATE INDEX IF NOT EXISTS idx_mol_silver_pub_pmid        ON mol_silver.publications(pmid);
        CREATE INDEX IF NOT EXISTS idx_mol_silver_pub_year        ON mol_silver.publications(publication_year);
        CREATE INDEX IF NOT EXISTS idx_mol_silver_pub_source      ON mol_silver.publications(source);
    END IF;
END $$;

-- ─── 2. mol_silver.molecule_publications (view) ──────────────────────────────
-- A molecule-scoped window onto mol_silver.publications.
-- Queried by xenon agents as /molecule_publications?molecule_id=eq.<uuid>.

DROP VIEW IF EXISTS mol_silver.molecule_publications CASCADE;
CREATE VIEW mol_silver.molecule_publications AS
SELECT
    id              AS publication_id,
    molecule_id,
    doi,
    pmid,
    title,
    abstract,
    first_author_name,
    journal_name,
    publication_year,
    publication_date,
    cited_by_count,
    concepts,
    mesh_terms,
    keywords,
    source
FROM mol_silver.publications
WHERE molecule_id IS NOT NULL;

-- ─── 3. Grants ───────────────────────────────────────────────────────────────

GRANT SELECT ON mol_silver.publications         TO analyst;
GRANT SELECT ON mol_silver.publications         TO authenticator;
GRANT SELECT ON mol_silver.publications         TO web_anon;
GRANT SELECT ON mol_silver.molecule_publications TO analyst;
GRANT SELECT ON mol_silver.molecule_publications TO authenticator;
GRANT SELECT ON mol_silver.molecule_publications TO web_anon;

-- ─── 4. Register in ops.sync_schedules ───────────────────────────────────────

INSERT INTO ops.sync_schedules (source, tier, cron_expression, priority, enabled, options)
VALUES
  ('openalex_ci', 'weekly', '0 3 * * 3', 'normal', true,
   '{"source_name":"OpenAlex CI","api_type":"rest","target_table":"mol_raw.openalex_ci"}'::jsonb)
ON CONFLICT (source) DO NOTHING;
