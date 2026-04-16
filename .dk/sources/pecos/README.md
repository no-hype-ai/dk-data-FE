# pecos

**Domain:** hcp
**Tier:** T1 — free CMS provider-characteristics download, no auth
**Fetch:** http_csv, monthly
**Status:** stub — tracking issue: #328

## Purpose
PECOS (Provider Enrollment, Chain, and Ownership System) publishes monthly CSV extracts of Medicare-enrolled providers and suppliers — the enrollment-truth companion to NPPES. Landing PECOS lets `hcp_silver.resolve_researcher` and `hcs_silver.resolve_provider` disambiguate active billing entities from inactive/historical NPI registrations.

## Upstream
- URL: https://data.cms.gov/provider-characteristics/medicare-provider-supplier-enrollment
- API docs: CMS public-use file metadata at same portal
- Rate limits: none documented (CDN-served bulk file)
- Auth: none

## Expected schema
- Target schema: `hcp_raw.pecos` → `hcp_bronze.pecos` → `hcp_silver.provider_enrollment`
- Known columns: `npi`, `pecos_asct_cntl_id`, `enrllmt_state_cd`, `provider_type_cd`, `specialty_cd`, `org_name`, `first_name`, `last_name`, `gender_cd`, `practice_address_zip`
- Row-count estimate: ~2.5M enrolled providers/suppliers

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
