# research_orgs_ror

**Domain:** hcp
**Tier:** T1 — public Zenodo JSON dump, no auth
**Fetch:** http_json_paginated, monthly
**Status:** stub — tracking issue: #338

> Note: the upstream is a single monthly JSON dump on Zenodo rather than a paginated live API; the `http_json_paginated` fetch kind is chosen for shape compatibility with dk-data's generic JSON fetcher and will iterate the dump's internal record array.

## Purpose
Research Organization Registry (ROR) is the open persistent-identifier registry for research organizations, maintained via monthly Zenodo dumps. ROR seeds dk-data's affiliation normalization in `hcp_silver`, letting us canonicalize employer/institution strings from NIH RePORTER, OpenAlex, Crossref, and PubMed into one researcher hub — a prerequisite for KOL and institution-level research-output analytics.

## Upstream
- URL: https://zenodo.org/communities/ror-data (monthly full JSON dump; each release has a DOI and stable download URL)
- API docs: https://ror.readme.io/docs/data-dump and https://api.ror.org/ (companion REST API for per-record lookups)
- Rate limits: Zenodo bulk download: none documented; ROR REST API: ~2k req/5min
- Auth: none

## Expected schema
- Target schema: `hcp_raw.research_orgs_ror` → `hcp_bronze.research_orgs_ror` → `hcp_silver.research_organizations`
- Known columns: `id` (ROR ID URL), `name`, `types[]` (Education / Healthcare / …), `country_code`, `country_name`, `aliases[]`, `acronyms[]`, `labels[]`, `external_ids` (GRID, ISNI, FundRef, Wikidata), `established` (year)
- Row-count estimate: ~110k organizations (growing ~1% monthly)

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
