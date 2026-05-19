-- Wave B: seed meta.source_registry for three aligned sources.
--
-- cms_open_payments, pecos, and nih_reporter all have live fetchers,
-- CronJobs, and descriptor YAMLs. This migration inserts them into
-- meta.source_registry so the CLI, dashboard, and admission controller
-- see them. Idempotent via ON CONFLICT DO NOTHING.
--
-- Closes: #327 (cms_open_payments), #328 (pecos), #329 (nih_reporter).

BEGIN;

SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '10s';

INSERT INTO meta.source_registry
  (name, domain, tier, depends_on, "fetch", schedule, credentials_ref,
   expected_row_count_sql, sla_seconds, manifest_path, consumes, status)
VALUES
  -- cms_open_payments: hcs domain, tier 5, annual CSV
  ('cms_open_payments', 'hcs', 5, '[]'::jsonb,
   '{"kind": "http_csv", "url": "https://download.cms.gov/openpayments/PGYR2024_P01302025.zip"}'::jsonb,
   '0 6 15 10 *', 'none',
   $$SELECT reltuples::bigint FROM pg_class WHERE relname='cms_open_payments'$$,
   7200, '.dk/sources/cms_open_payments.manifest.json',
   '{"wal_headroom_pct": 3, "db_connections": 2}'::jsonb, 'live'),

  -- pecos: hcp domain, tier 5, monthly CSV
  ('pecos', 'hcp', 5, '[]'::jsonb,
   '{"kind": "http_csv", "url": "https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment"}'::jsonb,
   '0 6 1 * *', 'none',
   $$SELECT reltuples::bigint FROM pg_class WHERE relname='cms_pecos'$$,
   3600, '.dk/sources/pecos.manifest.json',
   '{"db_connections": 2}'::jsonb, 'live'),

  -- nih_reporter: hcp domain, tier 5, weekly CSV
  ('nih_reporter', 'hcp', 5, '[]'::jsonb,
   '{"kind": "http_csv", "url": "https://reporter.nih.gov/exporter"}'::jsonb,
   '0 10 * * 0', 'none',
   $$SELECT reltuples::bigint FROM pg_class WHERE relname='nih_reporter'$$,
   3600, '.dk/sources/nih_reporter.manifest.json',
   '{"db_connections": 2}'::jsonb, 'live')

ON CONFLICT (name) DO NOTHING;

COMMIT;
