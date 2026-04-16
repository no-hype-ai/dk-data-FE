# cms_hac_reduction

**Domain:** hcs
**Tier:** T1 — free CMS provider-data portal CSV, no auth
**Fetch:** http_csv, annual
**Status:** stub — tracking issue: #324

## Purpose
CMS Hospital-Acquired Condition (HAC) Reduction Program publishes annual penalties for hospitals in the worst-performing quartile on HAC measures (CLABSI, CAUTI, SSI, MRSA, CDI, PSI 90). Landing this alongside HRRP and VBP completes dk-data's hospital-quality trio and feeds facility scorecards consumed by drug-product commercial teams and payer coverage analytics in `hcs_gold`.

## Upstream
- URL: https://data.cms.gov/provider-data/dataset/ypbt-wvdk
- API docs: CMS Provider Data Catalog REST API — https://data.cms.gov/provider-data/api
- Rate limits: none documented (CDN-served CSV)
- Auth: none

## Expected schema
- Target schema: `hcs_raw.cms_hac_reduction` → `hcs_bronze.cms_hac_reduction` → `hcs_silver.facility_quality_hac`
- Known columns: `facility_id` (CCN), `facility_name`, `state`, `total_hac_score`, `payment_reduction` (bool), `fy_start_date`
- Row-count estimate: ~3k hospitals × 1 row/year → ~3k rows/year

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
