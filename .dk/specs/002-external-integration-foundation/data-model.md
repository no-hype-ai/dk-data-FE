# Data Model — external-integration-foundation

> Canonical entities introduced or materially modified by this initiative. Field lists are business-level; exact types resolve to existing warehouse columns or generated code.

## Consuming App

An external application that reads from dk-data through the metering proxy gateway.

**Key attributes**:
- `name`: canonical identifier (e.g., `behavior-labs-ai`)
- `alias`: short form for audit logs (e.g., `blai`)
- `allowed_schemas`: explicit list of schemas this consumer can read
- `rate_limit`: requests per minute
- `tier`: `standard | high | unlimited`
- `api_keys`: list of provisioned credentials

**Relationships**:
- Has many `Consumer Credential`
- Issues requests validated at `Gateway Token` minting time

**Validation**:
- `allowed_schemas` MUST NOT be `["*"]` for any external consumer
- `api_keys` MUST be non-empty before the consumer is considered active
- `tier=unlimited` is reserved for internal cluster services and requires operator approval

**Storage**: `k8s/apps/metering-proxy/base/configmap.yaml`

---

## Client Package

The standardized typed library every consumer uses.

**Key attributes**:
- `package_name`: `@datakinetic/dk-data-client` (TS) or `dk-data-client` (Py)
- `version`: semver (major.minor.patch)
- `supported_modes`: `["strict", "upstream", "hydrate"]` (v0.1 supports strict + upstream only)
- `supported_errors`: 7 typed error classes (see Error Taxonomy below)
- `cache_ttl_table`: per-resource freshness windows

**Relationships**:
- Generates types from dk-data OpenAPI snapshot
- Emits `Telemetry Event` to Loki per call
- Calls `Gateway Token` minting endpoint on each uncached request

**Cache TTL table**:

| Resource type | L2 TTL | Rationale |
|---|---|---|
| Molecule identifiers / structural properties | 30 days | Immutable once assigned |
| Drug labels / regulatory status | 24 hours | Regulatory changes are daily-cadence |
| Clinical trials | 6 hours | Recruitment status can change mid-day |
| Adverse events / safety signals | 24 hours | FAERS updates are quarterly; 24h is safe |
| Publications | 24 hours | PubMed indexes daily |
| Competitive landscape | **24 hours** (corrected post-drift-audit) | Gold aggregation rebuilds nightly at 22:00 UTC via the SQLMesh transform cron — a 6h TTL would cache the same miss 4× per day |
| Lifecycle stages | 24 hours | Same refresh cadence (gold nightly) |
| Molecule profile | 24 hours | Same refresh cadence (gold nightly) |
| Company pipeline | 24 hours | Same refresh cadence (gold nightly) |
| Resolution queue / pipeline status | never cache | Operational state, must be live |

**Error taxonomy**:

| Class | Trigger | Caller action |
|---|---|---|
| `DkDataAuthError` | 401 from gateway or warehouse | Refresh API key, retry once |
| `DkDataForbiddenError` | 403 — schema not in consumer allowlist | Log + skip; ops adds schema |
| `DkDataNotFoundError` | 404 or empty result in strict mode | Handle "unknown entity" semantically |
| `DkDataStaleError` | 200 with `last_refreshed_at` older than threshold | Decide: use stale or refresh |
| `DkDataUpstreamError` | Fallthrough hit but upstream also failed | Retry or surface "unavailable" |
| `DkDataRateLimitError` | 429 from gateway | Auto-retry with backoff; only thrown after exhaustion |
| `DkDataServerError` | 5xx | Auto-retry; only thrown after exhaustion |

---

## Molecule

A canonical drug/compound entity in the silver hub.

**Key attributes**:
- `id`: UUID canonical identifier
- `inchi_key`: structural key (nullable for biologics)
- `generic_name`, `brand_names[]`
- `drug_type`, `regulatory_status`
- `therapeutic_areas[]`, `mechanism_of_action`
- `targets[]`, `identifiers` (CAS, UNII, PubChem, ChEMBL, DrugBank, RxCUI)
- `pharmacology` (ADME + half-life + protein binding)
- `data_sources[]`: provenance records
- `created_at`, `updated_at`

**Relationships**:
- Referenced by `Molecule Profile` (gold aggregation)
- Resolved via `mol_silver.resolve_molecule()` (Resolve Operation)
- Linked to `Clinical Trial`, `Drug Label`, `Safety Signal` (all in mol_api)

**Source of truth**: `mol_silver.molecules` (verified: silver hub table materialized by SQLMesh)

---

## Molecule Profile

The full gold-layer aggregated view of a molecule.

**Key attributes**:
- Extends `Molecule` with:
- `lifecycle_stages[]`, `competitive_landscape`, `safety_signals[]`
- `regulatory_timeline[]`, `clinical_trial_summary`
- `data_completeness_score`

**Relationships**:
- Derived from `Molecule` + all gold aggregations (`mol_gold.molecule_profile`, `safety_signals`, `lifecycle_stages`, `competitive_landscape`, `regulatory_timeline`, `trial_outcomes`, `company_pipeline`)

**Source of truth**: `mol_api.get_molecule_details(inchi_key) → JSONB`

**Key constraint (US-10)**: Exactly one canonical gold table — `mol_gold.molecule_profile` (singular) OR `mol_gold.molecule_profiles` (plural). Current state has both; US-10 consolidates to one.

---

## Silver Hub

A canonical entity-resolution hub for one of 10 entity types.

**Hub catalog**:

| Hub | Schema | Key tables | Resolve function |
|---|---|---|---|
| Molecule | `mol_silver` | `molecules`, `molecule_identifiers`, `molecule_names` | `resolve_molecule()` |
| Drug Product | `mol_silver` | `drug_products`, `drug_product_identifiers`, `drug_product_names`, `drug_product_ingredients` | `resolve_drug_product()` |
| Company | `mol_silver` | `companies`, `company_identifiers`, `company_names` | `resolve_company()` |
| Target | `mol_silver` | `targets`, `target_identifiers`, `target_names`, `target_sequences` | `resolve_target()` |
| Provider | `hcs_silver` | `providers`, `provider_identifiers`, `provider_names` | `resolve_provider()` |
| Facility | `hcs_silver` | `facilities`, `facility_identifiers`, `facility_names` | `resolve_facility()` |
| Condition | `ind_silver` | `conditions`, `condition_identifiers`, `condition_names` | `resolve_condition()` |
| Researcher | `hcp_silver` | `researchers`, `researcher_identifiers`, `researcher_names` | `resolve_researcher()` |
| Patent | `ip_silver` | `patents`, `patent_identifiers`, `patent_names` | `resolve_patent()` |
| Trademark | `ip_silver` | `trademarks`, `trademark_identifiers`, `trademark_names` | `resolve_trademark()` |
| Design | `ip_silver` | `designs`, `design_identifiers`, `design_names` | `resolve_design()` |

All 11 resolve functions are STABLE PARALLEL SAFE and exist as of migrations 178–188.

---

## Resolve Operation

A function that canonicalizes a name or identifier to a hub ID.

**Key attributes**:
- `entity_type`: one of the 11 hubs
- `input`: name OR identifier (any type the hub knows about)
- `output`: `{canonical_id, confidence, match_tier, alternatives?}`

**Match tiers** (ordered by confidence):
1. Exact identifier match (InChI key, ChEMBL ID, etc.)
2. Exact normalized name match
3. Trigram similarity above threshold (0.3 default)
4. Fallback to name-only fuzzy

**Invariants**:
- STABLE PARALLEL SAFE (Postgres function attribute)
- p99 latency ≤ 10 ms (per silver hub spec SC-004)
- Deterministic for the same input

---

## Consumer Credential

The API key issued to a consuming app.

**Key attributes**:
- `key`: `dk_data_{alias}_{16-char-suffix}`
- `consumer_id`: FK to Consuming App
- `allowed_schemas`: inherited from Consuming App at mint time
- `rate_limit_budget`: per-minute window
- `created_at`, `rotated_at`, `revoked_at?`

**Validation**:
- Key MUST match the format regex
- Revoked keys MUST be rejected by the gateway
- Rotation MUST be non-disruptive (old + new valid for overlap window)

**Storage**: `k8s/apps/metering-proxy/base/configmap.yaml` (populated via Platform API)

---

## Gateway Token

The short-lived credential the gateway mints for the warehouse read layer.

**Key attributes**:
- `role_claim`: `analyst` or `api_user`
- `consumer_id`: origin consumer (for audit)
- `issued_at`, `expires_at` (short TTL, e.g., 5 minutes)
- `signature`: HS256 over the claims using `JWT_SECRET`

**Relationships**:
- Minted from validated `Consumer Credential`
- Verified by PostgREST `PGRST_JWT_SECRET` and by FastAPI `verify_jwt` dependency

**Invariants**:
- Expiry MUST be short enough to limit replay attack window
- Role claim MUST be one of the allowed roles (`analyst`, `api_user`) — legacy `web_anon` is rejected as an invalid role

---

## Anonymous Role (to be dropped)

The legacy role that granted unauthenticated read access.

**Current state** (before migration 218):
- Name: `web_anon`
- Login: NOLOGIN
- Grants: USAGE on `api`, `hcs_silver`, `hcs_gold`, `hcs_agents`, `mol_agents`, `agents`, 4 raw CMS PUF tables, all silver hub canonical tables, materialized api views, 10 CI publication views
- Membership: granted to `authenticator` (so PostgREST falls back to it for unauthenticated requests)

**Target state** (after migration 218):
- Does not exist
- `PGRST_DB_ANON_ROLE` is unset in k8s configmap, docker-compose, standalone postgrest.conf

**Rollback**: `218_drop_web_anon_rollback.sql` restores only: USAGE on `api`, SELECT on `api.health`, SELECT on `api.data_catalog`.

---

## Metric

A monitoring counter, gauge, or histogram.

**Key attributes**:
- `name`: e.g., `dk_pipeline_processing_duration_seconds`
- `type`: `Counter | Histogram | Gauge | Summary`
- `labels[]`
- `emission_sites[]`: list of code locations that emit this metric
- `dashboard_references[]`: list of dashboard panels that query this metric

**Invariant (three-way binding, US-12)**: A metric is valid only if `emission_sites.length > 0 AND dashboard_references.length > 0`. Violations fail CI.

**Current state**: 78 defined, 40 live, 38 dead. US-12 closes the gap.

---

## Dashboard

A Grafana visualization that queries metrics and logs.

**Catalog (verified — 5 existing)**:

| UID | Title | Panels | Source |
|---|---|---|---|
| `cms-pipeline-health` | CMS PUF Data Pipeline | 53 | Prometheus |
| `dk-data-api-services` | dk-data API Services | 1 | Prometheus, container |
| `dk-data-pipeline-sources` | dk-data Pipeline & Sources | 133 | Prometheus, kube-state |
| `dk-data-platform-status` | dk-data Platform Status | 66 | Prometheus, kube-state |
| `dk-data-transformations` | dk-data Transformations | 54 | Prometheus, PostgreSQL |

**New dashboard (US-1 / US-7)**:

| UID | Title | Panels | Source |
|---|---|---|---|
| `dk-data-adapter-telemetry` | Adapter Hydration Heat Map | ~10 (hit/miss/fallthrough per method, p99 latency, top fallthroughs, per-consumer breakdown) | Loki |

**Invariant**: All dashboards filter by `job="dk-data-platform"` — the Prometheus scrape job name must match.

---

## Lineage Edge

A dependency between two warehouse models (source → target).

**Key attributes** (verified: `meta.model_lineage`):
- `source_model`, `target_model`
- `source_schema`, `target_schema`
- `source_layer`, `target_layer` (raw | external | bronze | silver | gold)
- `domain` (mol | hcs | ind | mart | scoring)
- `subdomain` (e.g., `mol-clinical-fda`, `hcs-provider`)
- `updated_at`

**Relationships**:
- Built by `src/dk_data/ingestion/utils/build_model_lineage.py`
- Visualized by `dk-data-transformations.json` nodeGraph panels

**US-11 additions**:
- New subdomain `ind-terminology` for UMLS, SNOMED, ICD-10/11, MeSH, ATC
- `mol_api` and `ip_api` added to `_SKIP_SCHEMAS` (presentation layer, not lineage)

---

## Data Source

An upstream fetcher that populates raw tables.

**Key attributes**:
- `source_name`: canonical name (aligned across backfill state, raw table, ingestion module — US-20)
- `raw_table`: destination table
- `bronze_descendants[]`, `silver_descendants[]`, `gold_descendants[]`
- `subdomain_classification`: which `*_SUBDOMAINS` bucket
- `refresh_cadence`: daily / weekly / monthly / quarterly
- `backfill_state`: `active | paused | failed | complete`

**US-20 alignment** (6 current mismatches to fix):

| Old backfill_state name | Raw table | Canonical (proposed) |
|---|---|---|
| `epo_ops` | `ip_raw.epo_patents` | `epo_patents` |
| `chembl_molecules` | `mol_raw.chembl` | `chembl_molecules` (rename raw table) |
| `cochrane` | `mol_raw.cochrane_reviews` | `cochrane_reviews` |
| `ema_mol` | `mol_raw.ema` | `ema` (rename backfill_state) |
| `hta_bodies` | `mol_raw.hta_decisions` | `hta_decisions` |
| `hrsa` | `hcs_raw.hrsa_shortage_areas` | `hrsa_shortage_areas` |

---

## Cronjob

A scheduled k8s job that fetches or transforms data.

**Key attributes**:
- `name`: k8s CronJob name
- `schedule`: cron expression
- `source`: which Data Source it targets
- `orchestrator_driven`: whether the backfill orchestrator parameterizes it
- `last_success_at`
- `last_failure_at`

**US-20 reductions**:
- 17 per-year `fetch-chembl-activities-{2010..2026}` → 1 parameterized
- 6 per-range `fetch-pubchem-range-{1..6}` → 1 parameterized
- Delete 2 dead jobs (`cms-puf-all`, `cms-cost-reports-puf-lines`)
- Net: 25 fewer files
