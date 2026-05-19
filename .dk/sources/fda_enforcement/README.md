# fda_enforcement

**Domain:** mol
**Tier:** T2 — free openFDA API key recommended (40→240 req/min); usable without
**Fetch:** http_json_paginated, daily
**Status:** fetcher_ready — tracking issue: #330

> Note: D.2 PR #318 seeded a descriptor at `.dk/sources/openfda_enforcement.yaml` for this endpoint. Plan §E.2 names this source `fda_enforcement`; onboarding should decide whether to alias/rename or keep the existing descriptor.

## Purpose
openFDA `/drug/enforcement.json` publishes drug recalls and enforcement reports (Class I/II/III) with product description, distribution pattern, reason for recall, and status. Landing daily keeps dk-data's recall-tracking and safety-signal surfaces current for commercial-risk and clinical-safety consumers of `mol_gold`.

## Upstream
- URL: https://api.fda.gov/drug/enforcement.json
- API docs: https://open.fda.gov/apis/drug/enforcement/
- Rate limits: 40 req/min unauthenticated; 240 req/min with free API key; 1000 results/page, deep-paging via `search=_exists_:...&skip=...`
- Auth: none required (free API key recommended for headroom)

## Expected schema
- Target schema: `mol_raw.fda_enforcement` → `mol_bronze.fda_enforcement` → `mol_silver.drug_recall_events`
- Known columns: `recall_number`, `classification`, `product_description`, `reason_for_recall`, `recall_initiation_date`, `status`, `recalling_firm`, `distribution_pattern`
- Row-count estimate: ~25k historical records + ~2k new/year

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
