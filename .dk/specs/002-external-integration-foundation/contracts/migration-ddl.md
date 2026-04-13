# Contract: Migration DDL Sketches

> **⚠ DRAFT — VALIDATE AT MIGRATION WRITE TIME**
>
> Reference DDL for each of the 5 migrations in this initiative. These are sketches, not ready-to-apply SQL. **Every column list must be validated against the actual silver-layer schema before the migration is written at T067/T071/T073/T077/T131.**
>
> Known validation gates:
> - **Migration 216 `mol_api.publications` UNION**: source column shapes of `mol_api.pubmed_publications` and `mol_api.openalex_publications` must be audited (T153) — `pmid` vs `work_id` types, `authors` vs `authorships` JSON shapes, DOI nullability all differ. The UNION in the sketch below uses speculative coercions that will fail if the actual columns differ.
> - **Migration 216 `mol_api.boxed_warnings`/`contraindications`**: `mol_silver.drug_labels` columns verified as `boxed_warning` and `contraindications` (inline, text, nullable). Sketch below matches reality.
> - **Migration 218 `DROP ROLE`**: verify no `web_anon` sessions are active (T088c) and no other role inherits from `web_anon` before running.
> - **Migration 220 `meta.backfill_state`**: verify required columns (`source_name`, `status`, `last_year_processed`, `last_range_processed`, `last_run_at`) exist OR add them (T152a).
>
> **Post-migration T161 task reconciles this contract back to the actual migrations once they're written** — contracts follow code, not the reverse.

## 215_ci_views_domain_relocate.sql

```sql
-- US-6: relocate 10 unprefixed api.* CI views to mol_api.* / ip_api.*

BEGIN;

CREATE SCHEMA IF NOT EXISTS ip_api;
GRANT USAGE ON SCHEMA ip_api TO analyst, api_user;

-- mol_api destinations (8 views)
CREATE OR REPLACE VIEW mol_api.pubmed_publications       AS SELECT * FROM api.pubmed_publications;
CREATE OR REPLACE VIEW mol_api.openalex_publications     AS SELECT * FROM api.openalex_publications;
CREATE OR REPLACE VIEW mol_api.ema_regulatory_decisions  AS SELECT * FROM api.ema_regulatory_decisions;
CREATE OR REPLACE VIEW mol_api.journal_articles          AS SELECT * FROM api.journal_articles;
CREATE OR REPLACE VIEW mol_api.hta_decisions             AS SELECT * FROM api.hta_decisions;
CREATE OR REPLACE VIEW mol_api.cochrane_reviews          AS SELECT * FROM api.cochrane_reviews;
CREATE OR REPLACE VIEW mol_api.medical_news              AS SELECT * FROM api.medical_news;
CREATE OR REPLACE VIEW mol_api.sec_filings               AS SELECT * FROM api.sec_filings;

-- ip_api destinations (2 views)
CREATE OR REPLACE VIEW ip_api.uspto_patents              AS SELECT * FROM api.uspto_patents;
CREATE OR REPLACE VIEW ip_api.epo_patents                AS SELECT * FROM api.epo_patents;

-- Repoint the api.* aliases to their new homes (same view name, different body)
CREATE OR REPLACE VIEW api.pubmed_publications       AS SELECT * FROM mol_api.pubmed_publications;
CREATE OR REPLACE VIEW api.openalex_publications     AS SELECT * FROM mol_api.openalex_publications;
CREATE OR REPLACE VIEW api.ema_regulatory_decisions  AS SELECT * FROM mol_api.ema_regulatory_decisions;
CREATE OR REPLACE VIEW api.journal_articles          AS SELECT * FROM mol_api.journal_articles;
CREATE OR REPLACE VIEW api.hta_decisions             AS SELECT * FROM mol_api.hta_decisions;
CREATE OR REPLACE VIEW api.cochrane_reviews          AS SELECT * FROM mol_api.cochrane_reviews;
CREATE OR REPLACE VIEW api.medical_news              AS SELECT * FROM mol_api.medical_news;
CREATE OR REPLACE VIEW api.sec_filings               AS SELECT * FROM mol_api.sec_filings;
CREATE OR REPLACE VIEW api.uspto_patents             AS SELECT * FROM ip_api.uspto_patents;
CREATE OR REPLACE VIEW api.epo_patents               AS SELECT * FROM ip_api.epo_patents;

-- Grants on new prefixed views (authenticated roles only — NOT web_anon)
GRANT SELECT ON mol_api.pubmed_publications       TO analyst, api_user;
GRANT SELECT ON mol_api.openalex_publications     TO analyst, api_user;
GRANT SELECT ON mol_api.ema_regulatory_decisions  TO analyst, api_user;
GRANT SELECT ON mol_api.journal_articles          TO analyst, api_user;
GRANT SELECT ON mol_api.hta_decisions             TO analyst, api_user;
GRANT SELECT ON mol_api.cochrane_reviews          TO analyst, api_user;
GRANT SELECT ON mol_api.medical_news              TO analyst, api_user;
GRANT SELECT ON mol_api.sec_filings               TO analyst, api_user;
GRANT SELECT ON ip_api.uspto_patents              TO analyst, api_user;
GRANT SELECT ON ip_api.epo_patents                TO analyst, api_user;

COMMIT;

-- Post-migration: add "ip_api" to PGRST_DB_SCHEMAS in k8s configmap + docker-compose + standalone conf
-- Post-migration: NOTIFY pgrst, 'reload schema'
```

## 216_missing_mol_api_views.sql

```sql
-- US-4: create the 5 views consumers already call but that don't exist.
-- Depends on 215 (needs mol_api.pubmed_publications + mol_api.openalex_publications).

BEGIN;

-- Boxed warnings (sourced from mol_silver.drug_labels.boxed_warning inline column — VERIFIED)
CREATE OR REPLACE VIEW mol_api.boxed_warnings AS
SELECT
    dl.label_id,
    dl.molecule_id,
    dl.set_id,
    dl.boxed_warning AS warning_text,
    dl.approval_date
FROM mol_silver.drug_labels dl
WHERE dl.boxed_warning IS NOT NULL
  AND dl.boxed_warning <> '';

-- Contraindications (sibling column on same row)
CREATE OR REPLACE VIEW mol_api.contraindications AS
SELECT
    dl.label_id,
    dl.molecule_id,
    dl.set_id,
    dl.contraindications AS contraindication_text,
    dl.approval_date
FROM mol_silver.drug_labels dl
WHERE dl.contraindications IS NOT NULL
  AND dl.contraindications <> '';

-- Competitive scores (derive from mol_gold.competitive_landscape)
CREATE OR REPLACE VIEW mol_api.competitive_scores AS
SELECT
    cl.molecule_id,
    cl.indication,
    cl.approved_count,
    cl.phase3_count,
    -- simple score: weighted sum, adjust at implementation
    (cl.approved_count * 3.0 + cl.phase3_count * 1.5) AS score,
    cl.market_leaders
FROM mol_gold.competitive_landscape cl;

-- Companies (flatten the silver hub)
CREATE OR REPLACE VIEW mol_api.companies AS
SELECT
    c.company_id,
    c.canonical_name,
    array_agg(DISTINCT ci.identifier_value) FILTER (WHERE ci.identifier_value IS NOT NULL) AS identifiers,
    array_agg(DISTINCT cn.display_name)     FILTER (WHERE cn.display_name IS NOT NULL)     AS names,
    c.first_seen,
    c.last_seen
FROM mol_silver.companies c
LEFT JOIN mol_silver.company_identifiers ci ON ci.hub_id = c.company_id
LEFT JOIN mol_silver.company_names cn       ON cn.hub_id = c.company_id
GROUP BY c.company_id, c.canonical_name, c.first_seen, c.last_seen;

-- Publications (UNION of pubmed + openalex — depends on 215)
CREATE OR REPLACE VIEW mol_api.publications AS
SELECT
    'pubmed' AS source,
    pmid   AS external_id,
    doi,
    title,
    abstract,
    publication_date,
    authors,
    journal
FROM mol_api.pubmed_publications
UNION ALL
SELECT
    'openalex' AS source,
    work_id AS external_id,
    doi,
    title,
    abstract,
    publication_date,
    authorships::text AS authors,
    (primary_location->>'source_display_name')::text AS journal
FROM mol_api.openalex_publications;

-- Grants: analyst + api_user only (NOT web_anon — see US-2)
GRANT SELECT ON mol_api.boxed_warnings     TO analyst, api_user;
GRANT SELECT ON mol_api.contraindications  TO analyst, api_user;
GRANT SELECT ON mol_api.competitive_scores TO analyst, api_user;
GRANT SELECT ON mol_api.companies          TO analyst, api_user;
GRANT SELECT ON mol_api.publications       TO analyst, api_user;

COMMIT;
```

## 217_resolve_function_grants.sql

```sql
-- US-5: grant EXECUTE on all 11 silver-hub resolve functions to authenticated roles
-- Functions themselves already exist (migrations 178-188)

BEGIN;

GRANT EXECUTE ON FUNCTION mol_silver.resolve_molecule       TO analyst, api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_drug_product   TO analyst, api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_target         TO analyst, api_user;
GRANT EXECUTE ON FUNCTION mol_silver.resolve_company        TO analyst, api_user;
GRANT EXECUTE ON FUNCTION ind_silver.resolve_condition      TO analyst, api_user;
GRANT EXECUTE ON FUNCTION hcs_silver.resolve_provider       TO analyst, api_user;
GRANT EXECUTE ON FUNCTION hcs_silver.resolve_facility       TO analyst, api_user;
GRANT EXECUTE ON FUNCTION hcp_silver.resolve_researcher     TO analyst, api_user;
GRANT EXECUTE ON FUNCTION ip_silver.resolve_patent          TO analyst, api_user;
GRANT EXECUTE ON FUNCTION ip_silver.resolve_trademark       TO analyst, api_user;
GRANT EXECUTE ON FUNCTION ip_silver.resolve_design          TO analyst, api_user;

COMMIT;
```

## 218_drop_web_anon.sql

```sql
-- US-2: drop the anonymous read role entirely
-- Runs LAST among 215-218 so prior migrations can still touch web_anon during the transition

DO $$
DECLARE
    schema_name TEXT;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        RAISE NOTICE 'web_anon role does not exist — nothing to drop';
        RETURN;
    END IF;

    FOR schema_name IN
        SELECT DISTINCT table_schema
        FROM information_schema.role_table_grants
        WHERE grantee = 'web_anon'
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('REVOKE USAGE ON SCHEMA %I FROM web_anon', schema_name);
        EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM web_anon', schema_name);
    END LOOP;

    REVOKE web_anon FROM authenticator;
    DROP ROLE web_anon;
    RAISE NOTICE 'web_anon dropped — all PostgREST requests now require JWT';
END $$;
```

## 218_drop_web_anon_rollback.sql

```sql
-- Emergency rollback: restore the MINIMUM grants (not the full legacy set)
-- Runbook: docs/runbooks/rollback-web-anon-drop.md

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN
        CREATE ROLE web_anon NOLOGIN;
    END IF;

    GRANT web_anon TO authenticator;
    GRANT USAGE ON SCHEMA api TO web_anon;
    GRANT SELECT ON api.health       TO web_anon;
    GRANT SELECT ON api.data_catalog TO web_anon;
    -- NOTHING MORE. Broader grants re-open the holes US-2 closed.
END $$;

-- Post-rollback: revert PGRST_DB_ANON_ROLE to "web_anon" in k8s configmap; roll deployment
```

## 220_align_source_naming.sql

```sql
-- US-20 / issue #277: align meta.backfill_state source names with canonical raw table names
-- Does NOT rename raw tables (that would cause data churn). Aligns the backfill_state side.

BEGIN;

UPDATE meta.backfill_state SET source_name = 'epo_patents'         WHERE source_name = 'epo_ops';
UPDATE meta.backfill_state SET source_name = 'cochrane_reviews'    WHERE source_name = 'cochrane';
UPDATE meta.backfill_state SET source_name = 'ema'                 WHERE source_name = 'ema_mol';
UPDATE meta.backfill_state SET source_name = 'hta_decisions'       WHERE source_name = 'hta_bodies';
UPDATE meta.backfill_state SET source_name = 'hrsa_shortage_areas' WHERE source_name = 'hrsa';

-- chembl_molecules stays as-is; raw table rename (mol_raw.chembl → mol_raw.chembl_molecules)
-- is a separate coordinated change that must happen alongside SQLMesh model updates.

COMMIT;
```
