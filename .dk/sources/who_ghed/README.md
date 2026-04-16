# who_ghed

**Domain:** hcs
**Tier:** T1 — public WHO GHED portal, no auth
**Fetch:** http_csv, annual
**Status:** stub — tracking issue: #334

## Purpose
WHO Global Health Expenditure Database (GHED) is the authoritative country-level health-spending panel (public, private, OOP, per-capita, % of GDP) across ~190 countries. One of three pillars (with OECD Health and World Bank Health) that closes the plan's "global pricing/spend" gap from §E.2/E.3 and underpins cross-country HEOR consumers of `hcs_gold`.

## Upstream
- URL: https://apps.who.int/nha/database (bulk Excel + indicator-level CSV exports)
- API docs: GHED portal offers CSV downloads by indicator set; no formal REST API
- Rate limits: none documented
- Auth: none

## Expected schema
- Target schema: `hcs_raw.who_ghed` → `hcs_bronze.who_ghed` → `hcs_silver.global_health_expenditure`
- Known columns: `country_code` (ISO-3), `country_name`, `year`, `indicator_code`, `indicator_name`, `value`, `unit` (USD / % GDP / per-capita), `source`
- Row-count estimate: ~190 countries × 25 years × ~60 indicators → ~285k rows

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
