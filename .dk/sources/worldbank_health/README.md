# worldbank_health

**Domain:** hcs
**Tier:** T1 — open World Bank REST API, no auth
**Fetch:** http_json_paginated, annual
**Status:** stub — tracking issue: #335

## Purpose
World Bank health indicators (HNP — Health Nutrition and Population topic) expose health-system capacity, mortality, morbidity, and financing series at country-year granularity via a stable REST API. Pairs with WHO GHED and OECD Health to form the global-spend triad called out in §E.3 for `hcs_gold.global_health_expenditure` roll-ups.

## Upstream
- URL: https://api.worldbank.org/v2/topic/8/indicator?format=json (topic=8 Health)
- API docs: https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-api-documentation
- Rate limits: none documented but polite throttling recommended (~5 req/sec); paginated with `page=` and `per_page=` (max 20000)
- Auth: none

## Expected schema
- Target schema: `hcs_raw.worldbank_health` → `hcs_bronze.worldbank_health` → `hcs_silver.global_health_indicators`
- Known columns: `country_code` (ISO-3), `country_name`, `indicator_code`, `indicator_name`, `year`, `value`, `unit`, `decimal`
- Row-count estimate: ~250 indicators × ~260 country/region codes × ~60 years → ~3M rows (filterable by indicator whitelist)

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
