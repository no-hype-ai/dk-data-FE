# dk-data Data Catalog

**Feature**: 002-external-integration-foundation (US-16, T123)
**Last verified**: 2026-04-13

This catalog maps every externally-readable endpoint to the schema it reads from, the owner of that data, and the SLA consumers can expect. If you're integrating a new read surface, start here — then read `docs/consumer-onboarding.md` for the provisioning steps.

The catalog is organized by read path:

1. [PostgREST — `/rest/<table>`](#postgrest-endpoints)
2. [FastAPI `/data-platform/*`](#fastapi-data-platform-endpoints)
3. [Resolve RPC — `/rpc/resolve_*`](#resolve-rpc-endpoints)

All endpoints are served under `https://data.behaviorlabs.ai` and gated by the metering proxy.

## Conventions

- **Owner**: the squad or engineer responsible for keeping the data fresh and the schema stable
- **Freshness**: the expected maximum age between the upstream source publishing and dk-data serving
- **Access tier**: the JWT role the consumer's API key must map to (`analyst`, `api_user`, or either)
- **Schema**: the PostgreSQL schema the endpoint reads from (or `→` the table it resolves to)

Freshness SLAs are informational — they are enforced by the `dk_pipeline_last_success_timestamp` gauge per source and alerted in Grafana.

## PostgREST endpoints

Reached via `GET /<table>` with `Accept-Profile: <schema>`.

### Molecule domain

| Path | Schema | Owner | Freshness | Access |
|---|---|---|---|---|
| `/molecules` | `mol_silver` | Molecule squad | 24h | either |
| `/molecule_identifiers` | `mol_silver` | Molecule squad | 24h | either |
| `/molecule_names` | `mol_silver` | Molecule squad | 24h | either |
| `/drug_products` | `mol_silver` | Molecule squad | 24h | either |
| `/drug_product_identifiers` | `mol_silver` | Molecule squad | 24h | either |
| `/drug_product_ingredients` | `mol_silver` | Molecule squad | 24h | either |
| `/targets` | `mol_silver` | Molecule squad | 24h | either |
| `/companies` | `mol_silver` | Molecule squad | 24h | either |
| `/competitive_landscape` | `mol_gold` | Molecule squad | 24h | either |
| `/competitive_scores` | `mol_api` | Molecule squad | 24h | either |
| `/bioactivity` | `mol_silver` | Molecule squad | 24h | api_user |
| `/publications` | `mol_silver` | Research squad | 6h | either |
| `/pubmed_articles` | `mol_silver` | Research squad | 6h | either |
| `/cochrane_reviews` | `mol_silver` | Research squad | 24h | either |

### Healthcare system domain

| Path | Schema | Owner | Freshness | Access |
|---|---|---|---|---|
| `/providers` | `hcs_silver` | Platform squad | 24h | either |
| `/facilities` | `hcs_silver` | Platform squad | 24h | either |
| `/hospital_general_info` | `hcs_silver` | Platform squad | 30d | either |
| `/hospital_outcomes` | `hcs_gold` | Platform squad | 30d | either |
| `/cms_enrollment` | `hcs_silver` | Platform squad | 90d | either |
| `/cms_dual_eligible` | `hcs_silver` | Platform squad | 90d | either |

### Indication / condition domain

| Path | Schema | Owner | Freshness | Access |
|---|---|---|---|---|
| `/conditions` | `ind_silver` | Research squad | 24h | either |
| `/clinical_trials` | `ind_silver` | Research squad | 6h | either |
| `/trial_outcomes` | `ind_gold` | Research squad | 24h | either |

### HCP domain

| Path | Schema | Owner | Freshness | Access |
|---|---|---|---|---|
| `/researchers` | `hcp_silver` | Research squad | 24h | api_user |
| `/researcher_identifiers` | `hcp_silver` | Research squad | 24h | api_user |

### IP domain

| Path | Schema | Owner | Freshness | Access |
|---|---|---|---|---|
| `/patents` | `ip_silver` | Platform squad | 7d | either |
| `/trademarks` | `ip_silver` | Platform squad | 7d | either |

### Deprecated `api.*` CI views

These views remain for backwards compatibility during the 30-day cutover window set by migration 215. New consumers MUST read from the silver replacements. Each view has a `COMMENT ON VIEW` that points at the right replacement.

| Deprecated path | Read this instead |
|---|---|
| `/pubmed_publications` (schema `api`) | `mol_silver.pubmed_articles` or `mol_silver.publications` |
| `/openalex_publications` (schema `api`) | `mol_silver.publications` |
| `/cochrane_reviews` (schema `api`) | `mol_silver.cochrane_reviews` |
| `/medical_news` (schema `api`) | `mol_silver.medical_news` or `mol_silver.news_signals` |
| `/journal_articles` (schema `api`) | `mol_silver.journal_rss` |
| `/ema_regulatory_decisions` (schema `api`) | `mol_silver.ema_regulatory` or `mol_silver.regulatory_decisions` |
| `/hta_decisions` (schema `api`) | `mol_silver.nice_hta` |
| `/sec_filings` (schema `api`) | `mol_silver.financial_data` or `mol_silver.company_financials` |
| `/uspto_patents` (schema `api`) | `ip_silver.patents` |
| `/epo_patents` (schema `api`) | `ip_silver.patents` |

A follow-up migration (scheduled ~30 days after 215 lands) will DROP the deprecated views. See `src/dk_data/sql/migrations/215_deprecate_redundant_ci_views.sql` for details.

## FastAPI data-platform endpoints

Reached via `<METHOD> /data-platform/<path>` with `Authorization: Bearer <jwt>`. Every route carries the router-level `require_auth` dependency (T027).

| Path | Method | Purpose | Owner | Access |
|---|---|---|---|---|
| `/data-platform/health` | GET | Service liveness | Platform squad | public (no auth) |
| `/data-platform/metrics` | GET | Prometheus scrape | Platform squad | Prometheus only |
| `/data-platform/molecules/resolve` | POST | Resolve a molecule identifier or name | Molecule squad | either |
| `/data-platform/conditions/resolve` | POST | Resolve a condition (indication) | Research squad | either |
| `/data-platform/companies/resolve` | POST | Resolve a company | Molecule squad | either |
| `/data-platform/providers/resolve` | POST | Resolve a healthcare provider | Platform squad | either |
| `/data-platform/facilities/resolve` | POST | Resolve a facility (hospital) | Platform squad | either |
| `/data-platform/researchers/resolve` | POST | Resolve a researcher / KOL | Research squad | either |
| `/data-platform/patents/resolve` | POST | Resolve a patent | Platform squad | either |
| `/data-platform/trademarks/resolve` | POST | Resolve a trademark | Platform squad | either |
| `/data-platform/job-complete` | POST | Inbound job completion callback | Platform squad | api_user |
| `/data-platform/refresh` | POST | Trigger an incremental refresh | Platform squad | api_user |

## Resolve RPC endpoints

Reached via `POST /rpc/<function>` with a JSON body `{ "p_name_or_id": "...", "p_hint": "..." }`. These are the same silver-hub resolve functions called directly through PostgREST instead of the FastAPI wrappers. Grant set by migration 217.

| Path | Backing function | Owner | Latency p99 (target) |
|---|---|---|---|
| `/rpc/resolve_molecule` | `mol_silver.resolve_molecule` | Molecule squad | ≤ 10 ms |
| `/rpc/resolve_drug_product` | `mol_silver.resolve_drug_product` | Molecule squad | ≤ 10 ms |
| `/rpc/resolve_target` | `mol_silver.resolve_target` | Molecule squad | ≤ 10 ms |
| `/rpc/resolve_company` | `mol_silver.resolve_company` | Molecule squad | ≤ 10 ms |
| `/rpc/resolve_condition` | `ind_silver.resolve_condition` | Research squad | ≤ 10 ms |
| `/rpc/resolve_provider` | `hcs_silver.resolve_provider` | Platform squad | ≤ 10 ms |
| `/rpc/resolve_facility` | `hcs_silver.resolve_facility` | Platform squad | ≤ 10 ms |
| `/rpc/resolve_researcher` | `hcp_silver.resolve_researcher` | Research squad | ≤ 10 ms |
| `/rpc/resolve_patent` | `ip_silver.resolve_patent` | Platform squad | ≤ 10 ms |
| `/rpc/resolve_trademark` | `ip_silver.resolve_trademark` | Platform squad | ≤ 10 ms |
| `/rpc/resolve_design` | `ip_silver.resolve_design` | Platform squad | ≤ 10 ms |

All resolve functions are `STABLE PARALLEL SAFE` per feature 001 (SC-004). The p99 target is enforced by `dk_silver_resolve_latency_seconds{function=...}`.

## Ownership at a glance

| Squad | Schemas owned | Primary contact channel |
|---|---|---|
| Molecule squad | `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_api` | `#molecule-data` |
| Research squad | `ind_*`, `hcp_*`, `mol_silver.publications` | `#research-data` |
| Platform squad | `hcs_*`, `ip_*`, `meta`, `staging` | `#data-platform` |
| Infra squad | `xenon`, `application`, `agents` | `#dk-data-infra` |

## Related

- `docs/architecture.md` — layered architecture and auth flow diagrams
- `docs/consumer-onboarding.md` — provisioning a new consumer
- `docs/runbooks/` — per-incident debugging runbooks
- `k8s/apps/metering-proxy/base/consumers.yaml` — canonical consumer registry
- `src/dk_data/sql/migrations/` — the migration files that created/granted every schema listed above
- `CLAUDE.md` — schema carve-outs, silver hub reference, agents collision notes
