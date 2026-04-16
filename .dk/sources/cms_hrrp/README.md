# cms_hrrp

**Domain:** hcs
**Tier:** T1 — free CMS provider-data portal CSV, no auth
**Fetch:** http_csv, annual
**Status:** stub — tracking issue: #325

## Purpose
CMS Hospital Readmissions Reduction Program (HRRP) publishes excess-readmission ratios and payment-reduction factors per hospital across six condition cohorts (AMI, HF, pneumonia, COPD, CABG, THA/TKA). Core hospital-quality benchmark; pairs with HAC and VBP for `hcs_gold` facility scorecards used in commercial targeting and payer analytics.

## Upstream
- URL: https://data.cms.gov/provider-data/dataset/9n3s-kdb3
- API docs: CMS Provider Data Catalog REST API — https://data.cms.gov/provider-data/api
- Rate limits: none documented (CDN-served CSV)
- Auth: none

## Expected schema
- Target schema: `hcs_raw.cms_hrrp` → `hcs_bronze.cms_hrrp` → `hcs_silver.facility_quality_hrrp`
- Known columns: `facility_id` (CCN), `measure_id` (READM_30_AMI, READM_30_HF, …), `excess_readmission_ratio`, `predicted_readmission_rate`, `expected_readmission_rate`, `number_of_discharges`, `fiscal_year`
- Row-count estimate: ~3k hospitals × 6 measures × 1 row/year → ~18k rows/year

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
