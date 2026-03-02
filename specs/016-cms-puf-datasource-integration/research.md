# Research: CMS PUF Data Source Integration

**Phase 0 Output** | **Date**: 2026-03-01

## Research Tasks

### RT-01: CMS Socrata API Patterns

**Context**: ~15 of the 30 sources use the CMS data.cms.gov Socrata-style API. Need to understand pagination, rate limits, dataset discovery, and bulk download patterns.

**Decision**: Use CMS data.cms.gov Socrata V1 API with pagination (`offset`/`limit` params, limit=1000 per page). Bulk CSV preferred for initial historical load; API for incremental updates.

**Rationale**: CMS migrated from CKAN to Socrata-compatible REST API. The API endpoint pattern is `https://data.cms.gov/data-api/v1/dataset/{dataset-id}/data` with JSON responses. Bulk CSV download endpoints are available for datasets >100K rows. Pagination uses `offset` + `limit` (not cursor-based). No authentication required. Rate limit is ~1000 requests/hour unauthenticated (based on empirical testing; no official documentation). `Retry-After` headers provided on 429 responses.

**Alternatives Considered**:
- Direct CKAN API: Deprecated by CMS in 2024. URLs still redirect but unreliable.
- Socrata SODA API (`$where`, `$select`): Some CMS datasets support this, but coverage is inconsistent. The V1 data-api endpoint is universally available.
- Full bulk-only approach: Would work for annual datasets but lose incremental capability for monthly/quarterly sources.

---

### RT-02: NPPES Bulk CSV Handling (9.3 GB)

**Context**: The NPPES monthly download file is 9.3 GB uncompressed CSV. Need a strategy for memory-efficient loading without OOM.

**Decision**: Use `pandas.read_csv(chunksize=50000)` for streaming processing. Resume-on-failure via tracking last processed row offset in `meta.data_sources`. Download via `requests.get(stream=True)` with 8KB chunk writes to disk before processing. Monthly CronJob with 8-hour `activeDeadlineSeconds`.

**Rationale**: 9.3 GB / 50K rows per chunk ≈ 160 chunks × ~3 sec/chunk = ~8 minutes processing time, well within 8-hour deadline. Memory footprint stays under 512 MB. Resume support avoids re-downloading 9.3 GB on transient failures. Pandas `chunksize` is the established pattern in the codebase (existing CMS inpatient fetcher uses similar approach).

**Alternatives Considered**:
- `polars` lazy frames: Better performance but introduces new dependency not in existing stack.
- PostgreSQL `COPY FROM` with `PROGRAM`: Fastest, but requires CSV file accessible from PostgreSQL server, which is not always the case in K8s.
- Stream directly from HTTP to DB without disk: Risky for 9.3 GB; network interruptions lose all progress.

---

### RT-03: PostgreSQL Range Partitioning Strategy

**Context**: Part D Prescribers (25M rows/year) and Physician PUF (10M rows/year) need partitioning by year. Need to determine partition strategy for raw + bronze layers.

**Decision**: PostgreSQL declarative range partitioning by `year INTEGER` column. Create partitions for years 2015-2025 at migration time. Annual partition creation via migration for new years. Both raw and bronze tables partitioned. Silver/gold tables NOT partitioned (aggregated, much smaller).

**Rationale**: Range partitioning enables efficient partition-swap on annual refresh (drop old partition, create new one). Query performance: year-filtered queries only scan relevant partition. PostgreSQL 16 supports declarative partitioning natively with no application-level changes. The `year` column is always present in PUF datasets and is the natural partition key.

**Alternatives Considered**:
- Hash partitioning: Spreads data evenly but doesn't align with the annual refresh pattern.
- List partitioning: Functionally equivalent for integer years, but range partitioning is more idiomatic.
- No partitioning + indexes: Works for queries but annual refresh becomes expensive (DELETE + INSERT instead of DROP PARTITION + CREATE).
- TimescaleDB hypertables: Requires extension, adds dependency, overkill for annual data.

---

### RT-04: Entity Resolution Strategy

**Context**: Provider entities appear in 5+ sources with potentially conflicting data (different addresses, phone numbers). Need a resolution strategy.

**Decision**: NPI is the canonical key — no fuzzy matching needed (unlike molecule resolution). NPPES is the authoritative source for demographics (source_precedence = 1). Other sources supplement: Care Compare (quality), Physician PUF (procedures), Part D (prescribing), Open Payments (payments). Silver-layer uses `DISTINCT ON (npi) ORDER BY source_precedence ASC` for conflicts. `entity_type` stored as text (`'individual'`, `'organization'`) not enum.

**Rationale**: NPI is a government-issued unique identifier with Luhn check digit. Unlike molecule names (acetaminophen vs. Tylenol vs. APAP), there's no ambiguity in NPI matching. The existing molecule pipeline uses fuzzy matching (InChI key, aliases); the provider pipeline can be much simpler. Source precedence is the standard approach for multi-source entity resolution when a canonical key exists.

**Alternatives Considered**:
- Fuzzy matching on provider name + address: Unnecessary given NPI uniqueness; would add complexity and false positives.
- Weighted scoring across sources: Over-engineered; NPPES is already the canonical source by CMS designation.
- `entity_type` as PostgreSQL enum: Text is simpler, doesn't require migration for new types, and matches the flexible JSONB-first approach.

---

### RT-05: Agentic Processing Architecture

**Context**: 6 agents need to process data from bronze/silver → silver/gold with LLM calls. Need architecture for batch processing, error handling, and cost control.

**Decision**: Extend existing `claude_sdk/` with `BaseAgent` ABC extracting common patterns from `enrichment.py` and `scoring_agent.py`. Monthly CronJobs. Three-tier validation: (1) Pydantic schema, (2) confidence thresholding (≥0.80 direct, 0.50-0.79 needs_review, <0.50 quarantine), (3) SQL integrity assertions. Use `claude-haiku-4-5-20251001` for cost efficiency. `meta.agent_execution_log` for audit, `meta.agent_quarantine` for low-confidence outputs.

**Rationale**: Existing `enrichment.py` (HospitalEnrichmentAgent) and `scoring_agent.py` (ScoringValidationAgent) share identical patterns: Anthropic client initialization, JSON extraction from LLM output, confidence scoring, result structuring. A `BaseAgent` ABC eliminates this duplication. Haiku pricing ($0.80/1M input, $4.00/1M output) keeps monthly cost under $400 even at maximum volume. The quarantine pattern prevents low-quality agent outputs from corrupting gold tables.

**Alternatives Considered**:
- Run agents in MCP invoke hot path: Latency too high (LLM call adds 2-5s). Monthly batch is appropriate for these enrichment tasks.
- Use GPT-4o instead of Claude Haiku: Higher cost, external vendor dependency, and the existing codebase already uses Claude models via LiteLLM proxy.
- No BaseAgent (copy-paste per agent): Duplicates error handling, logging, quarantine logic across 6 agents.
- Deterministic-only (no LLM): Works for ~80% of service line inference (DRG codes have deterministic mappings), but the remaining 20% ambiguous cases require semantic reasoning. IDN hierarchy and referral network have even higher ambiguity rates.

---

### RT-06: PostgREST Gold Schema Exposure

**Context**: Gold tables need to be exposed via PostgREST with proper access control. Need to understand schema exposure, RBAC, and query patterns.

**Decision**: Add `gold` to `PGRST_DB_SCHEMAS` in PostgREST configmap. RBAC: `GRANT USAGE ON SCHEMA gold TO analyst; GRANT SELECT ON ALL TABLES IN SCHEMA gold TO analyst`. `web_anon` gets NO access to gold. All gold table queries require analyst JWT.

**Rationale**: PostgREST supports multiple schemas via comma-separated list in `PGRST_DB_SCHEMAS`. The existing `analyst` role already has access to `mol_gold`; extending to `gold` is consistent. CMS provider/facility data is sensitive enough to require authentication (even though the source data is public, the aggregated profiles have commercial value). The `web_anon` exclusion matches the existing pattern where only `api.health` and `api.data_catalog` are unauthenticated.

**Alternatives Considered**:
- Expose gold via FastAPI endpoints instead of PostgREST: Would require custom endpoint code for each table; PostgREST provides filtering/pagination/sorting for free.
- Create a separate `cms_gold` schema: Would fragment the gold layer and require separate RBAC grants. The existing `gold` schema (currently unused) is the right place.
- Allow `web_anon` read-only access: Risk of unauthorized data scraping; analyst JWT requirement is consistent with `mol_gold` policy.

---

### RT-07: CMS Open Payments API

**Context**: Open Payments has its own API separate from the main data.cms.gov Socrata endpoint. Need to understand its API pattern.

**Decision**: Use the Open Payments API at `https://openpaymentsdata.cms.gov/api/1/datastore/query/{dataset-id}`. Supports JSON responses with pagination via `offset`/`limit`. Bulk CSV download available for historical data. No authentication required. Query by `Covered_Recipient_NPI` for provider lookups, by `Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name` for company lookups.

**Rationale**: The Open Payments API follows a slightly different pattern than data.cms.gov (different base URL, different dataset IDs), but the pagination and response format are similar enough to use the CMSSocrataFetcher base class with URL override. Annual data release in June covers the prior calendar year. Total dataset is 80M+ records across all years.

**Alternatives Considered**:
- Bulk-only download: Works for initial load, but doesn't support real-time MCP tool queries.
- Third-party Open Payments aggregators: Adds vendor dependency; the raw CMS data is comprehensive.

---

### RT-08: DDInter and Stabilis Dataset Caching

**Context**: DDInter 2.0 (302K drug-drug interactions) and Stabilis 4.0 (11.5K IV compatibility entries) are academic resources with unreliable API availability. Need an offline-capable strategy.

**Decision**: Full dataset download to raw table on first run. Quarterly refresh via CronJob. Fetcher operates in offline mode when API is unreachable (serve from cached raw data). MCP tool queries hit raw table directly, with bronze transformation for structured lookup.

**Rationale**: Both datasets are relatively small (302K and 11.5K records respectively). Full download to PostgreSQL is fast (<5 minutes) and enables offline operation. The academic APIs may have downtime or rate limiting that would make real-time lookups unreliable. Quarterly refresh is sufficient as these datasets change infrequently (major versions released ~annually).

**Alternatives Considered**:
- Real-time API proxying: Unreliable for academic APIs; latency would exceed MCP tool SLA.
- File-based caching (JSON/CSV on disk): Works but harder to query; PostgreSQL provides full-text search and structured filtering.
- SQLite sidecar database: Adds complexity; PostgreSQL is already available.

---

### RT-09: Health System (IDN) Hierarchy Construction

**Context**: Need to build Integrated Delivery Network hierarchies from PECOS + CHOW + Facility Affiliation data. Partially deterministic, partially requires agent inference.

**Decision**: Three-stage approach: (1) Deterministic: PECOS enrollment data directly maps provider NPIs to organization NPIs. Facility Affiliation provides facility CCN → organization NPI links. CHOW provides temporal ownership chains. (2) Heuristic: When PECOS/CHOW data is ambiguous or conflicting (e.g., mid-year merger), apply temporal precedence rules. (3) Agent: IDNHierarchy agent resolves remaining ambiguities (~150 systems) where multiple parent organizations claim the same facility. Agent cross-references against top 50 US health systems list for validation.

**Rationale**: ~80% of hierarchies can be constructed deterministically from PECOS + CHOW. The remaining 20% (mostly large multi-state systems with complex subsidiary structures) benefit from LLM reasoning about organizational naming patterns and geographic clustering. The top 50 US health systems cross-reference provides a ground truth baseline for validation.

**Alternatives Considered**:
- Fully deterministic (no agent): Misses 20% of complex hierarchies, particularly recent mergers.
- Fully agent-based: Unnecessary for the 80% deterministic case; wastes API budget.
- Manual curation: Doesn't scale; requires ongoing human maintenance as systems merge.

---

### RT-10: CMS Data Freshness and Staleness Monitoring

**Context**: 30 sources with different refresh cadences (daily, monthly, quarterly, annual). Need monitoring to detect stale data.

**Decision**: Use existing `dk_data_source_freshness_seconds` and `dk_data_source_staleness_seconds` Prometheus metrics. Each source registered in `meta.data_sources` with `refresh_frequency`. Staleness thresholds: monthly < 35 days, quarterly < 100 days, annual < 400 days. No new metrics infrastructure needed — existing metrics auto-cover new sources when registered.

**Rationale**: The existing observability infrastructure already computes freshness from `meta.data_sources.last_successful_refresh`. Adding new sources to the catalog table automatically enrolls them in freshness monitoring. The staleness thresholds include buffer time (e.g., monthly sources get 35 days, not 30) to accommodate CMS release schedule variability.

**Alternatives Considered**:
- Custom per-source monitoring: Overkill; the existing generic metrics cover all sources uniformly.
- AlertManager rules per source: Premature; start with metrics visibility and add alerts iteratively.

---

## Summary of Decisions

| Research Task | Decision | Impact |
|---------------|----------|--------|
| RT-01: CMS Socrata API | V1 data-api + bulk CSV, 1000/hr rate limit | Drives CMSSocrataFetcher design |
| RT-02: NPPES 9.3 GB CSV | pandas chunksize=50K, streaming download, resume-on-failure | Memory-safe ingestion |
| RT-03: Partitioning | Range by year for Part D + Physician PUF (raw + bronze) | Query performance + annual refresh |
| RT-04: Entity Resolution | NPI canonical key, NPPES authoritative, source precedence | Simple lookup, no fuzzy matching |
| RT-05: Agentic Processing | BaseAgent ABC, monthly CronJobs, Haiku, 3-tier validation | Cost control + quality assurance |
| RT-06: PostgREST Gold | Add `gold` to schemas, analyst-only access | Downstream product API |
| RT-07: Open Payments API | Separate API endpoint, CMSSocrataFetcher-compatible pagination | MCP tool + batch support |
| RT-08: DDInter/Stabilis | Full dataset cache, offline mode, quarterly refresh | Reliability for academic APIs |
| RT-09: IDN Hierarchy | 3-stage (deterministic → heuristic → agent) | 80% automated, 20% agent-assisted |
| RT-10: Freshness Monitoring | Existing metrics auto-cover, staleness thresholds | No new infra needed |

All NEEDS CLARIFICATION items resolved. No outstanding unknowns.
