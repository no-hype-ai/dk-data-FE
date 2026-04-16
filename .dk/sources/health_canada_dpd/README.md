# health_canada_dpd

**Domain:** mol
**Tier:** T1 — public Health Canada download, no auth
**Fetch:** zip, monthly
**Status:** stub — tracking issue: #333

## Purpose
Health Canada Drug Product Database (DPD) is the Canadian equivalent of Drugs@FDA — approved drug products with DINs, active ingredients, companies, schedules, pharmaceutical form, route, and status. Landing DPD gives dk-data a second Commonwealth regulator footprint and improves `mol_silver.drug_product_identifiers` crosswalk coverage.

## Upstream
- URL: https://www.canada.ca/en/health-canada/services/drugs-health-products/drug-products/drug-product-database/what-data-extract-drug-product-database.html (allfiles.zip)
- API docs: https://health-products.canada.ca/api/documentation/dpd-documentation-en.html (companion REST API)
- Rate limits: none documented for bulk ZIP
- Auth: none

## Expected schema
- Target schema: `mol_raw.health_canada_dpd` → `mol_bronze.health_canada_dpd` → `mol_silver.drug_product_approvals_ca`
- Known columns: `drug_code` (DIN), `brand_name`, `company_name`, `ingredient`, `strength`, `dosage_form`, `route_of_administration`, `schedule`, `class`, `status`
- Row-count estimate: ~50k active DINs + ~80k historical; ~10 pipe-delimited TXT files in the ZIP

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
