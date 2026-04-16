# cms_vbp

**Domain:** hcs
**Tier:** T1 — free CMS provider-data portal CSV, no auth
**Fetch:** http_csv, annual
**Status:** stub — tracking issue: #326

## Purpose
CMS Hospital Value-Based Purchasing (VBP) Program publishes total performance scores across clinical outcomes, person-and-community engagement, safety, and efficiency domains, plus payment-adjustment factors. Completes the hospital-quality trio (HAC/HRRP/VBP) required for a defensible `hcs_gold.facility_quality` scorecard.

## Upstream
- URL: https://data.cms.gov/provider-data/dataset/ypbt-wvdk (VBP dataset family on CMS provider-data portal)
- API docs: CMS Provider Data Catalog REST API — https://data.cms.gov/provider-data/api
- Rate limits: none documented (CDN-served CSV)
- Auth: none

## Expected schema
- Target schema: `hcs_raw.cms_vbp` → `hcs_bronze.cms_vbp` → `hcs_silver.facility_quality_vbp`
- Known columns: `facility_id` (CCN), `total_performance_score`, `clinical_outcomes_domain_score`, `person_community_engagement_score`, `safety_domain_score`, `efficiency_domain_score`, `payment_adjustment_factor`, `fiscal_year`
- Row-count estimate: ~3k hospitals × 1 row/year → ~3k rows/year

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
