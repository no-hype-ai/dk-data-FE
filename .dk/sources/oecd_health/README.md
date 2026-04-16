# oecd_health

**Domain:** hcs
**Tier:** T1 — public OECD SDMX/CSV, no auth
**Fetch:** http_csv, annual
**Status:** stub — tracking issue: #336

## Purpose
OECD Health Statistics covers ~50 OECD and partner countries on health status, resources, utilization, spending, and pharmaceutical market indicators. Completes the global-spend triad (WHO GHED + World Bank + OECD) for ex-US pricing and health-economics consumers of `hcs_gold` and underpins cross-country pharmaceutical-spend series.

## Upstream
- URL: https://stats.oecd.org/ (SDMX JSON/CSV endpoints) and https://data.oecd.org/health.htm
- API docs: https://data.oecd.org/api/sdmx-json-documentation/
- Rate limits: none documented; SDMX endpoint serves large datasets — chunk by dataset ID and year range
- Auth: none

## Expected schema
- Target schema: `hcs_raw.oecd_health` → `hcs_bronze.oecd_health` → `hcs_silver.oecd_health_indicators`
- Known columns: `country_code` (ISO-3), `country_name`, `dataset_id`, `indicator_code`, `indicator_name`, `year`, `value`, `unit`, `measure`
- Row-count estimate: ~50 countries × ~40 years × ~500 indicators → ~1M rows (filterable by dataset whitelist)

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
