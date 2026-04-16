# pbs_australia

**Domain:** mol
**Tier:** T1 — public PBS schedule download, no auth
**Fetch:** http_csv, monthly
**Status:** stub — tracking issue: #337

> Note: plan §E.2 calls out the upstream format as XML ("PBS XML schedule"); the `http_csv` kind tag here reflects that a CSV-flattened artifact is the intended bronze-landing shape. Descriptor should pick `http_csv` vs a new `xml`/`zip` kind during onboarding.

## Purpose
The Australian Pharmaceutical Benefits Scheme (PBS) publishes a monthly XML/CSV schedule of reimbursed medicines with brand, generic, restrictions, ingredients, and price-to-patient/dispensed fields. Landing PBS gives dk-data its first APAC reimbursement feed and ATC-linked pricing reference, complementing the global-spend triad with product-level pricing.

## Upstream
- URL: https://www.pbs.gov.au/info/industry/useful-resources/downloads (monthly PBS schedule ZIP with XML + CSV exports)
- API docs: https://data.pbs.gov.au/apex/f?p=PBS:2::GET::::: (PBS public API, same underlying dataset)
- Rate limits: none documented for bulk; public API is throttled to ~10 req/sec
- Auth: none

## Expected schema
- Target schema: `mol_raw.pbs_australia` → `mol_bronze.pbs_australia` → `mol_silver.drug_product_reimbursement_au`
- Known columns: `item_code` (PBS code), `brand_name`, `drug_name`, `manufacturer_code`, `form`, `strength`, `pack_size`, `atc_code`, `maximum_quantity`, `number_of_repeats`, `dispensed_price_max_qty`, `schedule_effective_date`
- Row-count estimate: ~6k item_codes × ~12 monthly schedules/year → ~72k rows/year

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
