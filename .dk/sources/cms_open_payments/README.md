# cms_open_payments

**Domain:** hcs
**Tier:** T1 -- free CMS Sunshine Act download, no auth
**Fetch:** http_csv, annual
**Status:** live

## Purpose
Open Payments (Sunshine Act) reports payments and transfers of value from drug/device manufacturers to physicians and teaching hospitals. Annual refresh with an October release. Landing this lets HCS silver models link payment flows to resolved providers and drug products.

## Upstream
- URL: https://download.cms.gov/openpayments/
- API docs: CMS Open Payments data dictionary at data.cms.gov
- Rate limits: none (CDN-served bulk ZIP)
- Auth: none

## Expected schema
- Target schema: `hcs_raw.cms_open_payments` -> `hcs_bronze.cms_open_payments` -> `hcs_silver.cms_facility_profile`
- Row-count estimate: ~12M payment records/year

## Fetcher
- `src/dk_data/ingestion/fetchers/cms_open_payments.py` (if present) or via generic `http_csv` path
- CronJob: `k8s/apps/cronjobs/base/cronjob-fetch-cms-open-payments.yaml`

## Descriptor
`.dk/sources/cms_open_payments.yaml`
