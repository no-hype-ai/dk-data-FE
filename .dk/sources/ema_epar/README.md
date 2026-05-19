# ema_epar

**Domain:** mol
**Tier:** T1 — public EMA bulk download, no auth
**Fetch:** http_csv, monthly
**Status:** stub — tracking issue: #332

## Purpose
EMA's European Public Assessment Reports (EPAR) bulk export is the EU counterpart to Drugs@FDA — every centrally-authorized medicine with status, therapeutic area, ATC code, authorization date, and active substance. Landing EPAR closes the biggest single gap in dk-data's ex-US regulatory coverage and feeds `mol_silver.drug_products` with EU approval identifiers.

## Upstream
- URL: https://www.ema.europa.eu/en/medicines/download-medicine-data
- API docs: EMA provides the bulk CSV/XLSX ("medicines output") — no public API; medicine and product detail pages are scraped per-product if needed
- Rate limits: none documented (direct CDN download)
- Auth: none

## Expected schema
- Target schema: `mol_raw.ema_epar` → `mol_bronze.ema_epar` → `mol_silver.drug_product_approvals_eu`
- Known columns: `medicine_name`, `active_substance`, `inn_common_name`, `atc_code`, `marketing_authorisation_holder`, `authorisation_status`, `marketing_authorisation_date`, `therapeutic_area`, `procedure_number`
- Row-count estimate: ~2.5k centrally authorized medicines

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
