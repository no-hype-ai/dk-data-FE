-- Migration 133: Create meta.model_lineage for SQLMesh DAG visualization
--
-- Stores pre-computed lineage edges derived by parsing SQLMesh SQL model files.
-- Populated by: src/dk_data/ingestion/utils/build_model_lineage.py
-- Consumed by: Grafana sqlmesh-lineage.json dashboard (Node Graph panels)
--
-- Edge: one row per source → target dependency (i.e., source appears in a FROM/JOIN
--       in the target model's SQL file).
--
-- Layers: raw | external | bronze | silver | gold
-- Domains: mol | hcs | ind | mart | scoring | targeting | staging
-- Subdomains: see build_model_lineage.py for mapping

CREATE TABLE IF NOT EXISTS meta.model_lineage (
    id              BIGSERIAL PRIMARY KEY,
    source_model    TEXT        NOT NULL,   -- e.g. mol_raw.clinicaltrials
    target_model    TEXT        NOT NULL,   -- e.g. mol_bronze.clinicaltrials
    source_schema   TEXT        NOT NULL,   -- e.g. mol_raw
    target_schema   TEXT        NOT NULL,   -- e.g. mol_bronze
    source_layer    TEXT        NOT NULL,   -- raw | external | bronze | silver | gold
    target_layer    TEXT        NOT NULL,
    domain          TEXT        NOT NULL,   -- mol | hcs | ind | mart | scoring
    subdomain       TEXT        NOT NULL,   -- e.g. mol-clinical-fda, hcs-provider
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source_model, target_model)
);

CREATE INDEX IF NOT EXISTS idx_model_lineage_domain
    ON meta.model_lineage (domain, subdomain);

CREATE INDEX IF NOT EXISTS idx_model_lineage_target
    ON meta.model_lineage (target_model);

COMMENT ON TABLE meta.model_lineage IS
    'Pre-computed SQLMesh model dependency graph. '
    'Rebuilt by build_model_lineage.py on each deploy. '
    'Used by Grafana sqlmesh-lineage dashboard Node Graph panels.';
