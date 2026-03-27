-- Migration: 085_bindingdb_sider_catalog
-- Purpose: Register BindingDB and SIDER in meta.data_sources catalog.
--          These sources have raw tables (migrations 062/028) and bronze/silver
--          models but were omitted from the catalog seed in migration 083.
-- Date: 2026-03-27

BEGIN;

INSERT INTO meta.data_sources (
    source_name, source_type, source_url, description, refresh_frequency, is_active
) VALUES
    (
        'bindingdb',
        'file',
        'https://www.bindingdb.org/bind/BindingDB_All.tsv.zip',
        'BindingDB drug-target binding affinity measurements (Ki, IC50, Kd, EC50)',
        'monthly',
        true
    ),
    (
        'sider',
        'file',
        'http://sideeffects.embl.de/media/files/',
        'SIDER side effect resource: drug-side effect associations from package inserts (MedDRA/UMLS)',
        'monthly',
        true
    )
ON CONFLICT (source_name) DO NOTHING;

COMMIT;

DO $$ BEGIN
    RAISE NOTICE 'Migration 085: Registered bindingdb and sider in meta.data_sources';
END $$;
