# Research: CMS PUF Data Source Integration

**Revised**: 2026-03-11

## Research Tasks

### RT-01: CMS Socrata API Patterns

**Status**: Complete

CMS uses Socrata Open Data API (SODA) for some datasets. Key findings:
- Rate limit: 1000 requests/hour unauthenticated, 10K with app token
- Supports `$limit`, `$offset`, `$where` for pagination
- Prefer bulk CSV downloads over API for full datasets (faster, no rate limit)
- Use API only for incremental/filtered updates

**Decision**: Use bulk CSV for annual/quarterly sources. Use API for monthly incremental sources (PECOS, NDC).

### RT-02: NPPES Bulk CSV Handling

**Status**: Complete

NPPES weekly export is ~8GB compressed. Key findings:
- Available from CMS at `https://download.cms.gov/nppes/`
- Use streaming download with MD5 hash check (existing `BaseFetcher` pattern)
- Process in 100K-row chunks to avoid OOM
- Upsert by NPI (ON CONFLICT DO UPDATE)
- Deactivated NPIs: keep in raw, filter in bronze

**Decision**: Streaming chunked reads. 100K batch upsert. Weekly CronJob.

### RT-03: PostgreSQL Range Partitioning

**Status**: Complete

Part D Prescriber (~25M rows/year) and Physician PUF (~10M rows/year) require partitioning.

- Partition by `year` column
- One partition per year (2019–current)
- PostgreSQL handles partition pruning automatically when `year` appears in WHERE
- PostgREST queries must include `year` filter for optimal performance
- SQLMesh models read from parent table (transparent)

**Decision**: Range partition by `year`. Document PostgREST query patterns in gold view comments.

### RT-04: Entity Resolution Strategy

**Status**: Complete

Provider entities span multiple sources (NPI in NPPES, Part D, Physician PUF, Open Payments).
Facility entities span POS, PECOS, Hospital Info, Quality.

- **Provider**: NPI is the universal key. All provider sources include NPI. No fuzzy matching needed.
- **Facility**: CCN is the universal key for CMS facilities. POS, PECOS, Hospital Info all use CCN.
- **Drug**: NDC is the universal key. Part D/B Spending, Formulary, NDC Directory all use NDC.

**Decision**: Deterministic key-based joins. No LLM-based entity resolution needed for base entities.

### RT-05: Agentic Processing Architecture

**Status**: Complete (revised 2026-03-11)

6 agents for Silver+ enrichment where SQL cannot reach.

- **LLM routing**: All calls via LiteLLM proxy using OpenAI-compatible Python client. Direct Anthropic SDK forbidden per dk-canon.
- **Model**: Haiku via LiteLLM alias. Budget: $175–385/month.
- **Execution**: K8s Jobs (not BullMQ — dk-data-FE is Python-only, no Node.js runtime).
- **Logging**: Append-only `meta.agent_execution_log`. No UPDATE/DELETE grants.
- **Quarantine**: Low-confidence records (< 0.5) written to `meta.agent_quarantine`.
- **Schedule**: Monthly via K8s CronJob.

**Decision**: K8s Jobs + LiteLLM + append-only logging + quarantine tier.

### RT-06: PostgREST Gold Schema Exposure

**Status**: Complete (revised 2026-03-11)

5 gold views exposed via PostgREST. No MCP tools.

- PostgREST `PGRST_DB_SCHEMAS` must include `gold`
- Views are materialized for query performance
- Daily refresh via CronJob
- Role-based access: `analyst` and `api_user` can read, `web_anon` cannot
- API views in `api` schema wrap gold views with additional filtering

**Decision**: PostgREST-only exposure. Consumers query directly. Cold-start handled by consumers calling external APIs.

### RT-07: CMS Open Payments API

**Status**: Complete

Open Payments data available via SODA API and bulk CSV.

- General payments: ~12M records/year
- Research payments: ~800K records/year
- Ownership: ~200K records/year
- Bulk CSV preferred (full dataset, no pagination needed)
- Record ID is unique across all three payment types

**Decision**: Bulk CSV download. Single fetcher handles all 3 payment types with `payment_type` discriminator.

### RT-08: DDInter/Stabilis Caching

**Status**: Complete

DDInter (drug-drug interactions) and Stabilis (IV compatibility) are external databases.

- DDInter: API access, ~500K interaction pairs, monthly refresh sufficient
- Stabilis: Web scraping needed, ~50K compatibility records, quarterly refresh
- Both are reference data — cache in raw, refresh on schedule
- No LLM needed for these sources

**Decision**: Standard fetcher + loader pattern. Monthly/quarterly CronJobs.

### RT-09: IDN Hierarchy Construction

**Status**: Complete

Integrated Delivery Networks (IDNs) are inferred from PECOS enrollment + CHOW ownership data.

- PECOS shows provider-to-organization relationships
- CHOW shows ownership change history → implies parent-child relationships
- No single source provides the full hierarchy
- Agent uses LLM to reason about ownership chains and infer structure

**Decision**: IDNHierarchy agent processes PECOS + CHOW data monthly. Confidence scores on inferred edges. Quarantine ambiguous relationships.

### RT-10: Cold-Start Strategy (New)

**Status**: Complete (added 2026-03-11)

When silver/gold tables are empty, downstream agents need data immediately.

**Analysis**:
- Previous approach: 30 MCP tools with table-read + API fallback
- Problem: Duplicates existing API clients in behavior-labs-ai (`@repo/data-sources`) and ground-truth-charlie (adapters)
- 30 tools × 2 code paths = 60 maintenance points in dk-data-FE

**Decision**: Remove MCP tools. Consumers query PostgREST first; if empty, they call external APIs using their own clients. dk-data-FE CronJobs populate tables on schedule. Cold-start is temporary and resolves after first ingestion cycle.

**Benefits**:
- dk-data-FE stays focused: fetch → transform → expose
- No duplication of API client logic
- Clear separation of concerns
- Simpler codebase to maintain
