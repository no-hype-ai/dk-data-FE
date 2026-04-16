# fda_shortages

**Domain:** mol
**Tier:** T2 — free openFDA API key recommended (40→240 req/min); usable without
**Fetch:** http_json_paginated, weekly
**Status:** stub — tracking issue: #331

## Purpose
openFDA `/drug/shortages.json` tracks current and resolved US drug shortages including reason, status, therapeutic category, and reporting company. Weekly cadence gives dk-data a timely supply-risk feed that integrates with drug_product commercial flows and payer coverage decisions in `mol_gold`.

## Upstream
- URL: https://api.fda.gov/drug/shortages.json
- API docs: https://open.fda.gov/apis/drug/shortages/
- Rate limits: 40 req/min unauthenticated; 240 req/min with free API key; 1000 results/page
- Auth: none required (free API key recommended)

## Expected schema
- Target schema: `mol_raw.fda_shortages` → `mol_bronze.fda_shortages` → `mol_silver.drug_shortage_events`
- Known columns: `generic_name`, `proprietary_name`, `status` (Currently in Shortage / Resolved), `shortage_reason`, `initial_posting_date`, `update_date`, `company_name`, `therapeutic_category`
- Row-count estimate: ~1.5k active + resolved entries; ~50 new/week

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
