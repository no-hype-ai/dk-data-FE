# Feature: Silver Medallion Rebuild

## Summary

Rebuild the dk-data silver layer on top of canonical entity-resolution hub tables so silver becomes a complete, indexed, single source of truth for downstream apps — and so every silver and transform activity stays inside the fixed CNPG cluster's hard ceilings on WAL, CPU, memory, and connections.

## User Scenarios & Testing

### US-1: Silver carries forward every bronze column (P1)

**As a** consumer of the dk-data silver layer, **I want** every silver table to expose every non-system column from its upstream bronze source(s), **so that** I never have to drop down to bronze to find a missing field and the medallion contract is honored.

**Acceptance Scenarios:**

```gherkin
Given a bronze table with non-system columns A, B, C, D
When the silver model that consumes it runs
Then the silver table contains A, B, C, D plus the entity-resolution columns the model adds

Given a silver model that aggregates multiple bronze sources
When detail-level fields exist in any of those sources
Then those detail fields are present in the same silver table — not aggregated away

Given a bronze column of type JSONB
When carried into silver
Then it is preserved as JSONB — not flattened, stringified, or selectively extracted

Given two bronze sources whose columns share a name
When merged into one silver row
Then the columns are prefixed with their source name to avoid collision
```

**Edge Cases:**
- A bronze table is dropped or replaced — silver models that depend on it must be updated in the same change.
- A new bronze source is added — must be wired into the appropriate hub before any silver model joins to it.
- Bronze schema changes that would require a migration on a table larger than ~1M rows are out of scope (this is the failure mode the rebuild exists to prevent).

### US-2: Entity resolution lives in canonical hubs and uses indexes (P1)

**As a** silver model, **I want** to obtain entity IDs (molecule_id, target_id, condition_id, provider_id, facility_id, company_id, drug_product_id, patent_id, trademark_id, design_id) by indexed lookup against canonical hubs, **so that** I do not re-derive entity linkage inline with OR-joins, leading-wildcard `LIKE`, correlated subqueries, or `DISTINCT ON` over multi-way unions.

**Acceptance Scenarios:**

```gherkin
Given a populated entity hub for an entity type
When a silver model needs the entity ID for a row
Then it obtains it via an indexed equi-join to the hub's identifier crosswalk
  or by calling the hub's resolve function

Given a silver model previously implemented as inline cross-source linkage
When rewritten to use the hub
Then the new model contains zero instances of the documented antipatterns
  (OR-joins on hub-eligible identifiers; leading-wildcard LIKE;
   correlated scalar subqueries; global DISTINCT ON over UNION ALL;
   trigram similarity combined with equality in the same OR clause)

Given a small molecule, a biologic without an InChIKey, and a combination drug
When each is resolved via the hub's resolve function
Then all three are correctly linked using the appropriate identifier tier
  for their entity sub-type
```

**Edge Cases:**
- Biologics have no structural canonical key — the molecule hub allows null structural keys and supports a sequence-hash plus identifier-based fallback tier.
- Combination drugs are products with multiple ingredients — represented as one product with N molecule references in a many-to-many ingredient table.
- Salt forms and stereoisomers have different structural keys but are clinically equivalent — the molecule hub supports a parent-pointer for clinical-grade rollup.
- Sources with no canonical identifier (some facilities, some companies, some narrative drug mentions) fall through to a name-based or fuzzy tier with an attached confidence score.

### US-3: Transformations fit inside the cluster's fixed budget (P1)

**As an** operator of the shared dk-data cluster, **I want** every silver and transform activity to stay inside the cluster's hard WAL, CPU, memory, and connection ceilings, **so that** no single dk-data activity can crash the postgres pod, starve other tenants, or repeat the prior incident in which a single transaction generated ~100 GB of WAL on a cluster that can only buffer 4 GB.

**Acceptance Scenarios:**

```gherkin
Given any silver or transform model running against full production data
When it executes
Then no single SQL transaction it produces exceeds 2 GB of WAL

Given any database connection opened by a dk-data workload
When it is established
Then it has client-side timeout, keepalive, and idle-in-transaction settings
  configured (because the server does not enforce them)

Given any long-running fetcher or short-lived transform pod
When it connects to postgres
Then it routes through the connection pooler unless it requires session-level
  features (advisory locks, prepared statements, server-side procedures)

Given any dk-data CronJob
When it is killed mid-run by an active deadline, OOM, network blip, or restart
Then the next scheduled run resumes from the last persisted checkpoint
  with zero duplicate inserts and no reprocessed work

Given the heaviest bronze and silver builds (large activity, binding, abstract, AE tables)
When they execute
Then they use chunked procedures with mid-loop commits
  and yield CPU between chunks to other tenants on the shared pod
```

**Edge Cases:**
- Monthly and seasonal stampedes (e.g., "0 0 1 * *" CronJobs all firing at once) must be staggered across hours or days.
- Cross-pod coordination must survive a connection-pooler in transaction mode (session-scoped advisory locks do not).
- Heavy fetcher payloads (multi-GB downloads) must support resume from byte offset on network failure.
- Raising session memory for a sort multiplies per-sort memory consumption — must be used carefully and documented per call site.

### US-4: The worst silver models are rewritten to use indexed hub joins (P2)

**As a** consumer waiting on broken or never-completing silver models, **I want** the silver models with the largest blast radius and the worst antipattern usage rewritten first, **so that** I see the visible payoff (slow models complete, broken models start working) and the downstream models that depend on them are unblocked.

**Acceptance Scenarios:**

```gherkin
Given the prioritized rewrite list (worst antipatterns + largest blast radius first)
When each silver model is rewritten to use indexed hub joins
Then it completes within its documented runtime budget on production data
  and produces row counts within the documented tolerance of the legacy output

Given a rewritten model whose legacy version contained banned antipatterns
When code review runs
Then the new version contains zero instances of those antipatterns
  and joins exclusively to hub crosswalk or name-index tables

Given two legacy models that the new hubs supersede outright
  (the all-source alias union and the all-source identifier union)
When the hubs are populated
Then the legacy models are deleted in the same PR as the molecule hub bootstrap
  (both are empty in the cluster today, so cutover risk is zero)
```

**Edge Cases:**
- A rewritten model's row count differs from the legacy output by more than the agreed tolerance — the discrepancy must be explained and documented before merge.
- Legacy model deletion requires verifying no consumer reads the table by name — a literal-name search across the consumer repositories is the gate.

### US-5: Free-text sources are linked via structured sibling fields the source APIs already provide (P3)

**As a** silver enrichment model for a source that ships data in narrative text (adverse events, clinical trial interventions, drug labels, abstracts, patent claims, news), **I want** to read the structured sibling fields the source API already populates alongside the prose, **so that** entity resolution happens at zero marginal cost without an LLM call.

**Acceptance Scenarios:**

```gherkin
Given a source whose API exposes harmonized identifier arrays alongside the prose
When a silver enrichment model resolves an entity for a row
Then it reads the harmonized field directly and joins to the relevant hub
  via the existing identifier crosswalk

Given a source whose API exposes pre-indexed concept lists (e.g., MeSH headings)
When a silver model needs to attach drug or condition mentions
Then it reads the pre-indexed list and joins through the corresponding crosswalk

Given a source where the only structured cross-reference is an identifier
  embedded in the abstract (e.g., a trial registry ID, a DOI, a PMID)
When the silver model enriches the row
Then a regex over the prose extracts the identifier and joins to the crosswalk
  by primary key
```

**Edge Cases:**
- A row has empty harmonized fields — the silver row is still written (US-1 contract) and the entity ID column is null.
- Cases that genuinely have no structured sibling field (some label prose sections, non-FDA patent claims, narrative deal terms) are out of scope for v1.
- LLM-based extraction is explicitly out of scope; if a future feature needs it, a follow-up will add it.

## Requirements

### Functional Requirements

**Column retention**

- **FR-001**: Every silver model MUST include every non-system column from its upstream bronze source(s) in its SELECT, in addition to any entity-resolution columns it adds. The exact "system column" exemption list is: `id`, `raw_id`, `ingested_at`, `request_timestamp`, `source`, `source_updated_at`, `processed_to_silver`, `processed_to_bronze`, `_loaded_at`, `raw_json`.
- **FR-002**: When two upstream bronze columns share a name, the silver model MUST disambiguate by prefixing each with its source name.
- **FR-003**: JSONB columns from bronze MUST be carried into silver as JSONB without flattening, stringification, or selective extraction.
- **FR-004**: Silver aggregation models MUST also expose the detail-level columns from their upstream sources — no summary-only / detail-dropped split.
- **FR-005**: A CI contract test MUST verify FR-001 for every silver model and fail the build on any missing non-system bronze column. The test MUST discover bronze upstream dependencies via the SQLMesh DAG (no live DB, no manifest file, no SQL comment annotation).

**Hub architecture**

- **FR-006**: The system MUST provide **eleven canonical hub tables across five schemas**: **`mol_*`** = Molecule / drug / compound; **`ind_*`** = Indication / disease / epidemiology; **`hcs_*`** = Healthcare system / CMS / provider; **`hcp_*`** = Healthcare professional / KOL / researcher; **`ip_*`** = Intellectual property (patents, trademarks, designs). The 11 hubs are: `mol_silver.molecules`, `mol_silver.drug_products`, `mol_silver.targets`, `mol_silver.companies`, `ind_silver.conditions`, `hcs_silver.providers`, `hcs_silver.facilities`, `hcp_silver.researchers`, `ip_silver.patents`, `ip_silver.trademarks`, `ip_silver.designs`.
**Full `ip_*` domain stack creation and migration (FR-006a–FR-006g)**

The `ip_*` (intellectual property) domain is currently absent from the cluster's actual postgres schemas. The dk-data SQLMesh transform orchestrator (`src/dk_data/ingestion/transform_molecules.py`) references `ip_bronze` / `ip_silver` / `ip_gold` as **layer names** in the LAYERS dict, but every model the orchestrator runs in those layers actually lives in `mol_raw` / `mol_bronze` / `mol_silver` / `mol_gold`. This is legacy debt — IP entities (patents, trademarks, designs) were originally lumped into the molecule domain because they "protect drugs". This feature creates the full `ip_*` medallion stack and migrates every IP-related fetcher, raw table, bronze model, silver model, gold model, and CronJob from `mol_*` to `ip_*`.

- **FR-006a — Schema registration**. The `ip_raw`, `ip_bronze`, `ip_silver`, `ip_gold` postgres schemas MUST be created via migration: `CREATE SCHEMA IF NOT EXISTS ip_raw; CREATE SCHEMA IF NOT EXISTS ip_bronze; CREATE SCHEMA IF NOT EXISTS ip_silver; CREATE SCHEMA IF NOT EXISTS ip_gold;`. PostgREST role grants on these schemas MUST follow the same pattern as the existing `mol_*` / `hcs_*` / `ind_*` grants (REVOKE from `web_anon`; GRANT SELECT to `analyst`, `mol_data_ops`, `mol_admin`).
- **FR-006b — SQLMesh config registration**. `src/dk_data/sqlmesh/config.yaml` `physical_schema_mapping` MUST add: `ip_raw: ip_raw`, `ip_bronze: ip_bronze`, `ip_silver: ip_silver`, `ip_gold: ip_gold`. The schema-domain comment block at the top of `physical_schema_mapping` MUST add a 5th line: `ip_*  — Intellectual property (patents, trademarks, designs) — protects drugs but is its own domain`.
- **FR-006c — Fetcher migration to `ip_raw`**. The 8 IP-related fetchers MUST be updated to write to `ip_raw.*` instead of `mol_raw.*`:
  - `src/dk_data/ingestion/fetchers/uspto_patents.py` → `ip_raw.uspto_patents`
  - `src/dk_data/ingestion/fetchers/uspto_ci.py` → `ip_raw.uspto_ci`
  - `src/dk_data/ingestion/fetchers/uspto_trademarks.py` → `ip_raw.uspto_trademarks`
  - `src/dk_data/ingestion/fetchers/epo_ops.py` → `ip_raw.epo_patents`
  - `src/dk_data/ingestion/fetchers/euipo_trademarks.py` → `ip_raw.euipo_trademarks`
  - `src/dk_data/ingestion/fetchers/euipo_designs.py` → `ip_raw.euipo_designs`
  - `src/dk_data/ingestion/fetchers/orange_book.py` — **stays in `mol_raw`** because Orange Book is a drug/patent crosswalk that primarily lives on the drug side; the FDA-drug → patent linkage join (FR-034) reads from `mol_bronze.orange_book` and joins to `ip_silver.patents`
  - `src/dk_data/ingestion/fetchers/purple_book.py` — **stays in `mol_raw`** for the same reason (Purple Book is a biologic/biosimilar registry; FR-037a/Gap 9 keeps it on the drug side)
  Each migrated fetcher MUST have its target schema parameter changed and its writes verified against the new `ip_raw.*` tables. The `seed_data_sources.sql` rows for these sources MUST update `silver_schema` from `mol_silver` to `ip_silver`.
- **FR-006d — Bronze model migration to `ip_bronze`**. The 7 IP-related bronze models MUST be moved from `src/dk_data/sqlmesh/models/molecules/bronze/` to `src/dk_data/sqlmesh/models/ip/bronze/` and their `MODEL (name ...)` declarations updated:
  - `mol_bronze.uspto_patents` → `ip_bronze.uspto_patents`
  - `mol_bronze.uspto_ci` → `ip_bronze.uspto_ci`
  - `mol_bronze.uspto_trademarks` → `ip_bronze.uspto_trademarks`
  - `mol_bronze.epo_patents` → `ip_bronze.epo_patents`
  - `mol_bronze.euipo_trademarks` → `ip_bronze.euipo_trademarks`
  - `mol_bronze.euipo_designs` → `ip_bronze.euipo_designs`
  - `mol_bronze.trademark_status_history` → `ip_bronze.trademark_status_history`
- **FR-006e — Silver model migration to `ip_silver`**. The 5 IP-related silver models MUST be moved from `src/dk_data/sqlmesh/models/molecules/silver/` to `src/dk_data/sqlmesh/models/ip/silver/` and their `MODEL (name ...)` declarations updated:
  - `mol_silver.patents` → `ip_silver.patents`
  - `mol_silver.trademarks` → `ip_silver.trademarks`
  - `mol_silver.patent_exclusivities` → `ip_silver.patent_exclusivities`
  - `mol_silver.trademark_status_changes` → `ip_silver.trademark_status_changes`
  - `mol_silver.euipo_designs` → `ip_silver.designs` (renamed for hub consistency)
- **FR-006f — Gold model migration**. The dependent gold model `mol_gold.company_pipeline` MUST be updated to read from `ip_silver.patents` and `ip_silver.trademarks` (currently reads from `mol_silver.*`). Any IP-specific gold models added by this feature MUST live in `ip_gold.*` (e.g., `ip_gold.patent_landscape`, `ip_gold.trademark_freedom_to_operate`).
- **FR-006g — CronJob, transform orchestrator, and PostgREST updates**.
  - The 8 IP-related CronJobs (`cronjob-fetch-uspto-patents.yaml`, `cronjob-fetch-uspto-ci.yaml`, `cronjob-fetch-uspto-trademarks.yaml`, `cronjob-fetch-epo.yaml`, `cronjob-fetch-euipo.yaml`, `cronjob-fetch-euipo-designs.yaml`) MUST have their env / args updated to point at the new `ip_raw.*` tables. Their `POSTGRES_HOST` env (FR-024) is unchanged.
  - `src/dk_data/ingestion/transform_molecules.py` `LAYERS` dict MUST update the `'ip_bronze'`, `'ip_silver'`, `'ip_gold'` entries so the listed model names are `ip_*.*` instead of `mol_*.*`. The `_get_marker_table()` map MUST be updated similarly.
  - PostgREST role grants on `ip_silver` MUST be added via migration. The existing role permissions on `mol_silver.patents` / `trademarks` MUST be revoked (the tables no longer exist after migration).
  - `meta.data_sources` rows for the 8 IP fetchers MUST update their `silver_schema` column.
- **FR-006h — Data migration**. The data migration from `mol_*` to `ip_*` MUST follow the chunked PL/pgSQL pattern (FR-021, FR-026): for each table, `INSERT INTO ip_<layer>.<table> SELECT * FROM mol_<layer>.<table>` is wrapped in a chunked procedure with mid-loop COMMITs (≤50K rows / ≤200 MB WAL per chunk). After verification (row count + sample comparison), the legacy `mol_<layer>.<table>` is dropped in the same PR.
- **FR-007**: Each hub MUST have a synthetic primary key, first-seen and last-updated timestamps, and only canonical fields — no source-specific data.
- **FR-008**: Each hub MUST have a paired identifier crosswalk keyed on `(source, identifier)` and a paired normalized name index keyed on `(normalized_name, hub_id, source)` with a `display_name` column preserving the original unnormalized spelling. The 3-column name-index PK is intentional: the same normalized name from two different sources is allowed and useful (one molecule may have separate INN and DrugBank entries for the same canonical name).
- **FR-009**: Each entity type MUST have a single resolve function that takes any combination of identifiers + a name and returns the canonical hub ID, walking the documented priority tree for that entity type. The resolve function MUST be the only place where resolution priority and disambiguation logic live.
- **FR-010**: All hub bootstrap procedures MUST read from existing bronze data and MUST NOT require any modification of raw or bronze schemas.
- **FR-011**: The molecule hub MUST support biologics (no structural canonical key), salt forms / stereoisomers (parent pointer), and combination drugs (separate product hub with many-to-many ingredient links).
- **FR-011b**: The system MUST provide an `hcp_silver.researchers` hub for healthcare professionals / KOLs / researchers as a distinct entity from `hcs_silver.providers`. Providers (`hcs_silver.providers`) are NPI-keyed regulatory entities (prescribers billable to Medicare). Researchers (`hcp_silver.researchers`) are publication-derived KOLs identified by ORCID + Scopus author ID + (PubMed first/last author + institution affiliation) + (ResearchGate / Google Scholar where available). The same person MAY have rows in BOTH hubs (a practicing oncologist who also publishes); the linkage between them lives in a `hcp_silver.researcher_provider_crosswalk` table keyed on `(researcher_id, provider_id)` populated from PubMed `AffiliationInfo` matched against NPPES practice locations. The researcher hub MUST cross-reference `mol_silver.molecules` (via PubMed `ChemicalList`), `ind_silver.conditions` (via PubMed `MeshHeadingList`), and `mol_silver.companies` (via institution affiliation when the affiliation resolves to an industry org).
- **FR-012**: The drug product hub MUST be at SCD/SBD-level granularity (one row per RxNorm Semantic Clinical Drug, e.g., "Sildenafil 50 MG Oral Tablet", regardless of how many NDC packages exist for it). NDC MUST live in the crosswalk (`source = 'ndc'`), not on the hub. The hub's only `UNIQUE` external-identifier constraint MUST be `(rxcui)` at SCD/SBD/GPCK/BPCK term type only.
- **FR-013**: The trigram fuzzy fallback (Pattern D) inside any resolve function MUST return null for matches with similarity below 0.85; matches at or above 0.85 MUST be returned with the computed `confidence` value. Gold-layer consumers and any clinical-grade silver join MUST filter on `confidence >= 0.95`.

**Antipattern bans**

- **FR-014**: Silver models MUST obtain entity-resolution columns by indexed equi-join to a hub crosswalk OR by calling the entity's resolve function — never by inline cross-source linking.
- **FR-015**: Silver models MUST NOT use OR-joins between two hub-eligible identifiers in a single join clause.
- **FR-016**: Silver models MUST NOT use leading-wildcard `LIKE` substring matching against indexed columns.
- **FR-017**: Silver models MUST NOT use correlated scalar subqueries in SELECT lists that re-execute per outer row.
- **FR-018**: Silver models MUST NOT use global `DISTINCT ON` over a multi-way `UNION ALL` of bronze tables.
- **FR-019**: Silver models MUST NOT combine trigram similarity with equality matchers in the same OR clause.
- **FR-020**: A CI job MUST grep silver model SQL for FR-015 through FR-019 antipattern signatures and fail the build on any match.

**Reliability and cluster fit**

- **FR-021**: No single SQL transaction produced by a dk-data workload MAY generate more than **500 MB** of WAL (per source reliability doc §9 self-imposed budget). Transformations that would exceed this MUST be chunked via procedures with mid-loop commits, target chunk size ≤50K rows / ≤200 MB WAL per chunk. The hard ceiling at the cluster level is `max_wal_size = 4 GB`; the 500 MB application budget gives an 8x safety margin so concurrent transactions cannot collectively trigger checkpoint storms.
- **FR-021a**: No dk-data CronJob run MAY generate more than **5 GB** of WAL total across all its transactions (per §9). Total dk-data WAL/day across the whole platform MUST stay under **50 GB**.
- **FR-021b**: No dk-data session MAY raise `work_mem` above **256 MB** via `SET LOCAL` (per §9). Heavy transforms MAY use `SET LOCAL work_mem = '128MB'` at the start of the relevant transaction; the 256 MB ceiling is per-session — a query with multiple sorts multiplies the per-sort memory.
- **FR-021c**: No dk-data statement MAY run longer than **5 minutes** (per §9). The client-side `statement_timeout` value (FR-022) MUST be set to 300000 ms (5 min) for fetcher and short-lived transform connections; PL/pgSQL procedure invocations and SQLMesh runs MAY use a longer value (10 min) but MUST NOT exceed it.
- **FR-021d**: No dk-data connection MAY hold an open transaction for longer than **30 minutes** (per §9). The `idle_in_transaction_session_timeout` MUST be set to 300000 ms (5 min) at the connection level (FR-022); the 30-minute ceiling is the absolute upper bound for procedure invocations and is enforced via `meta.activity_log` snapshot queries that flag any dk-data transaction running >30 min.
- **FR-021e**: At any moment dk-data MAY have at most **10 concurrent fetcher pods** and **3 concurrent transform pods** (per §9) running against postgres. Stampede staggering (FR-029) and per-pod advisory locks (FR-025) enforce this.
- **FR-021f**: dk-data activities collectively MUST NOT consume more than **80% of the postgres pod's 2 CPU budget** for sustained periods, leaving headroom for `behavior_labs` and `litellm`. Per-procedure `pg_sleep(0.05)` between chunks (FR-028) and the concurrency caps in FR-021e enforce this.
- **FR-022**: Every dk-data database connection MUST be opened with client-side timeout (`statement_timeout=300000ms` for fetchers/transforms = 5 min per FR-021c; `statement_timeout=600000ms` for SQLMesh and PL/pgSQL procedure invocations = 10 min), keepalive (`keepalives=1`, `keepalives_idle=60`, `keepalives_interval=10`, `keepalives_count=6`), `idle_in_transaction_session_timeout=300000ms` (5 min), and `lock_timeout=30000ms` — the server does not enforce these.
- **FR-023**: Every dk-data database connection MUST set `application_name` to the pod name so it is identifiable in `pg_stat_activity` (the cluster has no `pg_stat_statements`).
- **FR-024**: Long-running fetchers and short-lived transform connections MUST route through `pgbouncer.infra.svc.cluster.local:5432` unless they require session-level features (advisory locks, prepared statements, server-side procedures).
- **FR-025**: Cross-pod coordination MUST use a TTL-based persistent lock table `meta.job_locks` with at minimum the columns `(name text PRIMARY KEY, locked_by text NOT NULL, locked_at timestamptz DEFAULT NOW(), expires_at timestamptz NOT NULL)`. The table MUST survive connection-pooler transaction mode and MUST auto-expire stale locks. Session-scoped `pg_try_advisory_lock` MUST NOT be used.
- **FR-026**: Every dk-data CronJob and bootstrap procedure MUST be idempotent and resumable from a persisted checkpoint. The minimum schema for `meta.refresh_state` is `(procedure_name text PRIMARY KEY, last_chunk_position text NOT NULL, last_commit_at timestamptz DEFAULT NOW(), status text DEFAULT 'in_progress')`. Restarting an interrupted procedure MUST resume at `last_chunk_position` and MUST NOT reprocess already-committed chunks.
- **FR-026a**: All hub crosswalk tables MUST have `(source, identifier)` as `PRIMARY KEY`. Bootstrap inserts MUST use `ON CONFLICT (source, identifier) DO NOTHING`. If a re-run encounters an existing `(source, identifier)` that resolves to a different `hub_id` than the existing row, the bootstrap MUST log the conflict to `meta.linkage_conflicts (detected_at timestamptz, source text, identifier text, existing_hub_id bigint, new_hub_id bigint, procedure_name text)` and MUST NOT silently overwrite.
- **FR-027**: Heavy fetcher payloads (>1 GB) MUST be downloaded with HTTP range / resume support so a network blip does not force a restart from byte 0.
- **FR-028**: Hub bootstrap procedures MUST insert `pg_sleep(0.05)` between chunks to leave breathing room for behavior_labs and litellm tenants on the shared pod.
- **FR-029**: Stampede CronJob schedules (monthly "0 0 1 * *", seasonal April-15 CMS PUF refresh) MUST be staggered across hours or days so connection, CPU, and WAL ceilings are not all hit simultaneously.
- **FR-030**: All Python database connections MUST be opened via a single `dk_data.ingestion.utils.database.build_dsn()` helper that enforces FR-022 and FR-023 — no direct `psycopg2.connect()` calls outside the helper.

**Free-text source linking**

- **FR-031**: Silver enrichment models for sources that ship harmonized identifier arrays alongside narrative text (FAERS, openFDA labels, DailyMed) MUST read those harmonized arrays (`openfda.unii[]`, `openfda.rxcui[]`, `openfda.product_ndc[]`, `openfda.substance_name[]`) and resolve via the appropriate hub crosswalk. They MUST NOT call any LLM and MUST NOT parse the prose fields for entity extraction.
- **FR-032**: Silver enrichment models for ClinicalTrials.gov MUST read `protocolSection.derivedSection.interventionMeshList[]` and `conditionMeshList[]` and join via the MeSH crosswalk. The `interventionName` and `conditions` prose fields MUST NOT be parsed with an LLM.
- **FR-033**: Silver enrichment models for PubMed and EuropePMC MUST read `MeshHeadingList` and `ChemicalList` for drug and condition mentions, and MUST attach trial / publication cross-references via regex over title and abstract: `NCT\d{8}` for trials, `10\.\d{4,9}/[-._;()/:A-Z0-9]+` for DOIs, `PMID:?\s*\d+` for PMIDs.
- **FR-034**: Silver enrichment models for USPTO and EPO patents MUST attach `molecule_id` for FDA-approved drugs by joining `mol_bronze.orange_book` on `(application_number, patent_number)`. Patent claim prose MUST NOT be parsed in v1.
- **FR-035**: Silver enrichment models for medical news and journal RSS MUST detect drug mentions via a precompiled regex built at startup from `mol_bronze.who_inn` (~10K WHO INN entries). No LLM.
- **FR-036**: FAERS reactions MUST be resolved via `patient.reaction[].reactionmeddrapt` (already a MedDRA Preferred Term) — the reaction prose MUST NOT be parsed with an LLM.
- **FR-036e**: The `hcp_silver.researchers` hub MUST be populated from PubMed `AuthorList` + `AffiliationInfo` structured fields. Each PubMed record's authors are extracted via `pubmed.MedlineCitation.Article.AuthorList.Author[]` (each Author has `LastName`, `ForeName`, `Initials`, `Identifier[@Source='ORCID']`, `AffiliationInfo[].Affiliation`). The author signature (`lower(LastName) || '_' || lower(left(ForeName,1))`) plus institution + country populates `resolve_researcher` tier 6. ORCID iDs (when present in `Identifier[@Source='ORCID']`) populate tier 1. No LLM call. Optional cross-references from Scopus author IDs (via OpenAlex `openalex_ci.authorships[].author.scopus_id`) and ResearchGate / Google Scholar IDs (when available from cross-source enrichment) populate tiers 2, 4, 5.
- **FR-036f**: The `hcp_silver.researcher_provider_crosswalk` MUST be populated by fuzzy-matching `(researcher.canonical_full_name + researcher.primary_affiliation_institution + researcher.primary_affiliation_country)` against `(hcs_silver.providers.last_name + first_name + state)` joined with practice location addresses from `hcs_bronze.cms_nppes.practice_addresses[]`. Match confidence MUST be ≥0.85 to insert; gold consumers MUST filter `confidence ≥ 0.95` per FR-013b for any clinical-grade query that needs the provider/researcher join.
- **FR-036g**: The `hcp_silver.researcher_publications` and `hcp_silver.researcher_affiliations` cross-reference tables MUST be populated as part of the `bootstrap_researchers` procedure. Drug and condition cross-references for each publication are derivable by joining `researcher_publications.pmid` to `mol_silver.pubmed_articles.molecule_id` / `condition_id` (which are themselves resolved via `MeshHeadingList` + `ChemicalList` per FR-033). No new linkage logic — reuses the existing PubMed-side resolution.

**Tray pattern (UNLOGGED staging) for bulk bronze rebuilds — source reliability doc §4**

- **FR-037a**: For bronze refreshes of any table larger than 1M rows that needs DELETE+INSERT semantics, the system MUST use the tray pattern (UNLOGGED staging table → atomic swap) to convert ~100 GB single-transaction WAL to ~5 GB total WAL across the SET LOGGED operation. The 5 specific tables required to use this pattern are: `mol_bronze.chembl_activities` (highest priority — caused the 2026-04-10 incident), `mol_bronze.bindingdb`, `mol_bronze.clinicaltrials`, `mol_bronze.pubchem`, `mol_bronze.chembl_molecules`.
- **FR-037b**: Tray pattern procedures MUST be invoked via dedicated CronJobs (NOT the daily SQLMesh CronJob) and MUST connect via `POSTGRES_HOST_DIRECT` (not PgBouncer) so the procedure can hold session-level state across the chunked load → SET LOGGED → atomic swap sequence.

**BRIN, drop-recreate, and partitioning for write amplification — source reliability doc §6**

- **FR-038**: Bronze tables larger than 1M rows MUST use BRIN indexes on naturally clustered time columns (`ingested_at`, `request_timestamp`) instead of btree. BRIN is 100–1000x smaller and 10–100x faster to write for clustered columns. Existing btree indexes on these columns MUST be dropped after the BRIN index is created.
- **FR-039**: Bronze rebuild procedures (FR-037a tray pattern) MUST drop non-essential indexes (anything that is not a unique constraint supporting `ON CONFLICT`) before the chunked load and recreate them concurrently after. This avoids 30x WAL amplification from index writes during bulk load.
- **FR-040**: The 5 heaviest bronze tables (chembl_activities, bindingdb, clinicaltrials, pubchem, chembl_molecules) MUST be partitioned by month on `ingested_at`. Daily refreshes touch only the current month's partition; the other 99% of indexes are untouched. This is a one-time migration that pays for itself forever.

**Application-side monitoring (since no `pg_stat_statements`) — source reliability doc §10**

- **FR-041**: The system MUST provide a `meta.slow_query_log (label, elapsed_ms, pod_name, logged_at)` table populated by a Python `timed_query()` context manager that logs any DB operation exceeding a per-call slow threshold (default 1000 ms). This is the dk-data substitute for `pg_stat_statements`.
- **FR-042**: The system MUST provide a `meta.wal_usage (job_name, wal_mb, logged_at)` table populated at the end of every fetcher and transform CronJob run. WAL produced is measured by bracketing the run with `pg_current_wal_lsn() - '0/0'::pg_lsn`. Any single job producing >5 GB MUST trigger an alert.
- **FR-043**: The system MUST run a `meta.activity_log` snapshot CronJob every 60 seconds that captures non-idle `pg_stat_activity` rows for `datname = 'dk_data'` with their state, wait events, query age, and the first 500 chars of the query text. This enables post-incident "what was running at time T" investigations.
- **FR-044**: The system MUST run a `meta.wal_status` snapshot CronJob every 5 minutes that records `wal_files`, `wal_size_bytes`, `max_active_replication_lag_bytes`, and `max_inactive_replication_lag_bytes`. Alerts fire on `wal_size_bytes > 20 GB` (5x `max_wal_size`, indicates accumulation) and `max_inactive_lag_bytes > 1 GB` (dead replication slot).
- **FR-045**: Grafana MUST have alert rules for: `dk_data_slow_query` (any query >10s); `dk_data_wal_explosion` (any single CronJob produces >5 GB WAL); `dk_data_long_transaction` (any dk-data transaction runs >1 hour); `dk_data_activity_pile_up` (more than 50 active dk-data queries simultaneously).

**SQLMesh transform fixes — source reliability doc §3.2**

- **FR-046**: Heavy SQLMesh models that use `INCREMENTAL_BY_TIME_RANGE` and produce DELETE+INSERT semantics MUST be replaced with chunked PL/pgSQL procedures (FR-026 + FR-037a). Source doc T1.
- **FR-047**: Source data for `INCREMENTAL_BY_UNIQUE_KEY` SQLMesh models MUST be wrapped in a deduplicating CTE (`SELECT DISTINCT ON (key) ... ORDER BY key, ingested_at DESC`) before MERGE, to avoid inserting older versions when the source contains duplicates within a single time window. Source doc T3.
- **FR-048**: Heavy transforms that perform JSONB extraction, `DISTINCT ON`, or other memory-bound operations MUST set `SET LOCAL work_mem` at the start of the transaction. Per-session ceiling is 256 MB total (FR-021b). Source doc T4.
- **FR-049**: `FULL` gold models that rebuild the entire table per run MUST be converted to `INCREMENTAL_BY_UNIQUE_KEY` with a `last_modified` watermark wherever the underlying data has a stable identity column. Source doc T5.
- **FR-050**: SQLMesh models that depend on freshly-loaded bronze MUST start with an explicit staleness check that raises an exception if the upstream is older than a documented threshold (e.g., `max(ingested_at) < now() - interval '6 hours'`). Source doc T6.
- **FR-051**: The `mol-transform-bronze-ext` CronJob MUST have `activeDeadlineSeconds` set to at least 14400 (4 hours) — the bronze layer has 35 models including the heaviest. Source doc T7.
- **FR-052**: The `k8s/overlays/prod/kustomization.yaml` patch targeting the no-longer-existing `mol-transform` CronJob MUST be deleted or replaced with patches targeting the actual current names (`mol-transform-bronze-ext`, `mol-transform-silver-ext`, etc.). Source doc T8.

**PostgREST API fixes — source reliability doc §3.3**

- **FR-053**: A migration MUST set per-role `statement_timeout` and `idle_in_transaction_session_timeout` for every PostgREST role: `web_anon` 30 s / 60 s; `analyst` 5 min / 5 min; `api_user` 30 s / 60 s; `mol_viewer` 30 s; `mol_analyst` 5 min; `mol_data_ops` 30 min; `mol_admin` 1 hour. Source doc A1.
- **FR-054**: A migration MUST `REVOKE USAGE` on every non-`api` schema from `web_anon` and grant `web_anon` only `USAGE ON SCHEMA api` plus `SELECT ON ALL TABLES IN SCHEMA api`. Source doc A2.
- **FR-055**: PostgREST `PGRST_DB_POOL` MUST be increased from 10 to 30 (per replica) and `PGRST_DB_STATEMENT_TIMEOUT` MUST be set to 30s. With 3 replicas through PgBouncer this is 90 client slots, not 90 server slots. Source doc A3.
- **FR-056**: PostgREST liveness/readiness probes MUST switch from HTTP `/health` (which queries the DB) to TCP socket on port 3000. The current probes hit the DB 6 times/minute just for health checks. Source doc A4.
- **FR-057**: Hot dashboard queries SHOULD be backed by materialized views in the `api` schema (e.g., `api.facility_summary`, `api.molecule_summary`) refreshed nightly via a CronJob. Source doc A5.

**job-trigger fixes — source reliability doc §3.4**

- **FR-058**: `job-trigger` MUST scale to 2 replicas. Single-node K3s makes anti-affinity a no-op, but two replicas means a pod restart doesn't cause API downtime. Source doc J1.
- **FR-059**: The system MUST provide a `meta.job_runs (id, job_name, started_at, completed_at, status, pod_name, error_message, rows_processed)` table for in-flight job tracking. Status values: `running`, `succeeded`, `failed`, `killed`. Source doc J2.
- **FR-060**: `job-trigger` MUST recycle DB connections every N requests or M seconds (TTL) to prevent stale connections accumulating over the days/weeks the pod is up. Source doc J3.

**Backup CronJob fixes — source reliability doc §3.5**

- **FR-061**: The `pg_dump` backup CronJob MUST run at 12:00 UTC instead of 02:00 UTC. The current schedule overlaps with overnight fetchers; the snapshot prevents vacuum during heavy fetch windows. Source doc B1.
- **FR-062**: `pg_dump` and other backup CronJobs MUST have `activeDeadlineSeconds` set to at least 14400 (4h). pg_dump on a 100 GB DB takes 1–2 hours. Source doc B2.
- **FR-063**: The system SHOULD switch from `pg_dump` to `pg_basebackup` for the primary backup path. `pg_basebackup` streams without holding a long snapshot and doesn't block vacuum. Requires creating a dedicated replication slot first. Source doc B3.
- **FR-064**: dk-data MUST NOT run two parallel backup systems against the same database. The cluster has CNPG barman-cloud → SeaweedFS AND `pg_dump` → MinIO. Recommendation: keep `pg_dump` → MinIO as the primary (more reliable than the flaky barman-cloud). Source doc B4.
- **FR-065**: Automated restore testing MUST be added: a `pg_backup_verify` CronJob that spins up a temp postgres pod, restores the latest backup, runs sanity queries (row counts on major tables), and tears down. Currently the verifier only runs `pg_restore --list` which proves the file is parseable, not restorable. Source doc B5.

**Fetcher fixes (remaining) — source reliability doc §3.1**

- **FR-066**: PgBouncer pool sizes MUST be tuned per database in the PgBouncer configmap: `dk_data` pool_size 80, `behavior_labs` pool_size 50, `litellm` pool_size 20. PgBouncer also MUST be configured with `max_client_conn=1000`, `default_pool_size=20`, `reserve_pool_size=5`, `reserve_pool_timeout=3`. Source doc F9.
- **FR-067**: Heavy single-CronJob fetchers (chembl_activities, pubchem) MUST be split into smaller per-year or per-ID-range CronJobs so each runs in <2 hours and is independently retryable. Source doc F10.

**Tier 2 free-text source linking — source linkage doc**

- **FR-068**: Silver enrichment for the Tier 2 sources (`cms_open_payments`, `cms_part_d_prescriber`, `cms_opioid_puf`, `cms_ddinter`, `cms_stabilis`, `cms_usp`, `cms_magnet`, `hrsa`, `acc_tvc`) MUST use direct alias lookup with fuzzy fallback per the linkage doc Tier 2 table: `cms_open_payments.name_of_drug_or_biological_or_device_or_medical_supply` → `mol_silver.molecule_names` direct lookup; `cms_part_d_prescriber.brand_name + generic_name` → RxNorm BN/IN lookup; `cms_opioid_puf.brand_name + generic_name + ndc` → NDC canonical link; `cms_ddinter.drug_a + drug_b` → generic name lookup; `cms_stabilis.drug name` → generic name lookup; `cms_usp.usp_class + example drugs` → class is canonical; `cms_magnet.hospital_name + state` → trigram fuzzy → CCN; `hrsa.facility_name + address` → fuzzy/geocode → CCN+NPI; `acc_tvc.facility identifiers` → fuzzy → CCN.

**Legacy model handling**

- **FR-037**: The legacy `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` models MUST be deleted from the SQLMesh project in this feature, in the same PR as the molecule hub bootstrap. Both tables are empty in the cluster today, so cutover risk is zero. The only required safety check is a literal-name grep across `dk-data-FE`, `dk-flux`, `behavior-labs-web`, `xenon-repo`, and `dk-alchemy`; any hit must be triaged with the owning code's author before merge.

### Key Entities

| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Molecule hub | One row per real-world molecule (small molecule or biologic) | Synthetic ID, InChIKey (nullable for biologics), canonical SMILES, sequence hash, is_biologic flag, parent_molecule_id (for salts and stereoisomers), canonical name, first/last seen timestamps |
| Drug product hub | One row per RxNorm SCD/SBD clinical drug concept (NOT one per NDC package) | Product ID, RxCUI (UNIQUE at SCD/SBD/GPCK/BPCK), BLA + product number, NDA application + product number, EMA product number, CVX code, brand, generic, dosage form, route, strength normalized to mg, is_combination, is_biologic, is_biosimilar, reference_product_id |
| Drug product ingredients | Many-to-many link from products to ingredient molecules | Product ID, molecule ID, strength value, strength unit, is_active, ingredient_order |
| Target hub | One row per protein / receptor / enzyme target | Synthetic ID, UniProt ID, sequence hash, canonical name, first/last seen timestamps |
| Condition hub | One row per disease / indication / adverse event | Synthetic ID, ICD-10, ICD-11, MeSH descriptor ID, MedDRA PT, canonical name |
| Company hub | One row per pharma / biotech / academic / regulatory entity | Synthetic ID, CIK, ticker, normalized company name (after stripping `Inc.`/`Corp.`/`Ltd.`/etc.), country |
| Provider hub (`hcs_silver.providers`) | One row per US prescribing healthcare provider — NPI-keyed regulatory entity (Medicare-billable). NOT the same as the researcher hub. | Synthetic ID, NPI, PECOS ID, taxonomy code, last/first/middle name, specialty |
| Facility hub (`hcs_silver.facilities`) | One row per US healthcare facility / organization | Synthetic ID, CCN, NPI type-2, NCDR facility ID, facility name, city, state, ZIP, ownership type |
| Researcher hub (`hcp_silver.researchers`) | One row per KOL / academic researcher / publication author. Distinct from the provider hub — researchers are publication-derived (ORCID/Scopus/PubMed-keyed), providers are regulatory (NPI-keyed). The same person MAY have rows in BOTH hubs linked via a researcher↔provider crosswalk. | Synthetic ID, ORCID iD, Scopus author ID, PubMed first/last author signature, ResearchGate ID, Google Scholar ID, normalized full name, primary affiliation institution, h-index (if available), first/last publication year |
| Patent hub | One row per granted or pending patent | Synthetic ID, jurisdiction + patent_number, jurisdiction + application_number, jurisdiction + publication_number, PCT application, title, abstract, filing/grant/expiry dates, CPC codes, IPC codes, kind code, status |
| Trademark hub | One row per trademark registration | Synthetic ID, jurisdiction + registration_number, jurisdiction + serial_number, WIPO Madrid international registration number, mark text, mark type, Nice classes, registration/expiry dates, status, owner |
| Design hub | One row per industrial design registration | Synthetic ID, jurisdiction + design_number, WIPO Hague international design number, Locarno classes, filing/registration dates, holder, product indication |
| Identifier crosswalk (per hub) | One row per `(source, external_identifier)` pair pointing at a hub row | Source, identifier, hub ID, optional `is_primary` flag |
| Name index (per hub) | One row per `(normalized_name, hub_id)` pair for fuzzy / name-based resolution | Normalized name, hub ID, name kind (canonical/generic/brand/IUPAC/synonym/INN/research_code), source, confidence, display_name (original unnormalized spelling) |
| Resolve functions | One per entity type — encapsulates the priority tree from structural canonical → stable external ID → curated name → fuzzy | Walks the tree, returns canonical hub ID or null |
| Persistent job lock table | TTL-based lock table for cross-pod coordination that survives connection-pooler transaction mode | Lock name, holder, acquired-at, expires-at |
| Refresh checkpoint | Per-procedure resumption marker so any interrupted bootstrap or refresh resumes at the last committed chunk | Procedure name, chunk position, last commit timestamp |

## Success Criteria

- **SC-001** (column retention): 100% of silver models pass the column-retention CI contract test (every non-system bronze column appears in the silver SELECT).
- **SC-002** (hub coverage — molecules): After bootstrap, the molecule identifier crosswalk resolves at least 95% of distinct identifiers present across `mol_bronze.chembl_molecules`, `mol_bronze.drugbank`, `mol_bronze.pubchem`, `mol_bronze.rxnorm`, and `mol_bronze.fda_ndc` to a canonical molecule_id.
- **SC-003** (hub coverage — facilities): After bootstrap, the facility identifier crosswalk resolves at least 90% of distinct CCNs present across the CMS hospital, quality, PUF, and PECOS bronze tables to a canonical facility_id.
- **SC-004** (resolve function latency): Single-identifier lookups against any resolve function complete in under 10ms p99 against indexed crosswalks.
- **SC-005** (silver model runtime): The 10 silver models historically identified as the worst offenders all complete in under 10 minutes on full production data after rewrite.
- **SC-006** (WAL ceiling — per transaction): No single transaction produced by a dk-data workload exceeds 500 MB of WAL (FR-021). No CronJob run exceeds 5 GB total (FR-021a). Total dk-data WAL/day stays under 50 GB. Zero exceedances per week, measured via `meta.transform_runs.wal_bytes` and `meta.wal_usage.wal_mb`.
- **SC-007** (incident non-recurrence): The 2026-04-10 failure mode (single transaction generating >100 GB of WAL on `chembl_activities`) is impossible by design — every bronze and silver model touching tables larger than 1M rows uses chunked PL/pgSQL or is validated by an audit script that estimates WAL produced before merge.
- **SC-008** (hub bootstrap budget): The full hub bootstrap of all **11 hubs** completes in under **115 minutes** wall clock, produces under **7.5 GB** of WAL total, and never holds a row lock for more than 1 second. (Budget bumped from 105 min / 7 GB to absorb the new `hcp_silver.researchers` hub bootstrap from PubMed/ORCID/Scopus author lists, estimated ~8 min / ~500 MB WAL.)
- **SC-009** (multi-tenant impact): During hub bootstrap and silver rewrite runs, `behavior_labs` and `litellm` query p95 latency increases by no more than 10% over the baseline. Baseline is the rolling 7-day p95 of `application_name = 'behavior_labs'` and `application_name = 'litellm'` query latency captured from `pg_stat_activity` immediately before the bootstrap kicks off.
- **SC-010** (resumability): Killing any dk-data bootstrap or CronJob mid-run and restarting it produces the same final state as a single uninterrupted run, with zero duplicate rows in target tables.
- **SC-011** (PgBouncer routing): At least 90% of dk-data pod connections (excluding SQLMesh and PL/pgSQL procedure callers) terminate at PgBouncer rather than the postgres primary, measured by `pg_stat_activity.client_addr`.
- **SC-012** (antipattern eradication): A repository-wide grep of `src/dk_data/sqlmesh/models/**/silver/*.sql` returns zero matches for the antipattern signatures S1–S5 after rewrite.
- **SC-013** (FAERS coverage via structured fields): After the rewritten enrichment models run on the full bronze backlog, at least 70% of `mol_silver.adverse_events` rows have a non-null `molecule_id` (resolved from `openfda.unii` / `openfda.rxcui` / `openfda.substance_name`) and at least 85% have a non-null `condition_id` (resolved from `reactionmeddrapt`).
- **SC-014** (legacy model deletion): `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` are removed from the SQLMesh project in the same PR as the molecule hub bootstrap. Both tables verified empty in the cluster pre-merge; consumer-repo grep complete with zero unresolved hits.
- **SC-015** (connection-string safety): 100% of dk-data Python entry points obtain their DSN from `dk_data.ingestion.utils.database.build_dsn()`, verified by CI grep.

## Assumptions

- The fixed-infrastructure constraints documented in `transformation-reliability-low-tech-solutions.md` are out of scope for this feature. The application adapts to the cluster; it does not propose changes to the cluster, the postgres pod, the K3s topology, the connection pooler config, or the WAL archiver.
- The bronze layer is already populated and uses incremental-by-unique-key model kinds. This feature does not modify bronze schemas, bronze model kinds, or fetcher data shapes beyond the connection-string and idempotence fixes the reliability principles require.
- Re-ingestion of bronze data is not an option. All hub and crosswalk construction reads from existing bronze data only.
- Bronze schema migrations on tables larger than ~1M rows are intentionally out of scope — that is the failure mode this feature exists to prevent.
- The `litellm-server` deployment on penguin (VMID 100) is NOT called by this feature. Source-API audit found ~80–90% of cases originally assumed to need LLM extraction are already structured (openFDA harmonization arrays, ClinicalTrials.gov derivedSection MeSH lists, PubMed MeshHeadingList + ChemicalList, Orange Book for FDA-drug patents, WHO INN regex for news). The remaining ~10–20% (DailyMed indication prose, non-FDA patent claims, SEC EDGAR Business sections) is deferred to a follow-up feature.
- The existing PgBouncer deployment at `pgbouncer.infra.svc.cluster.local:5432` is reachable from all dk-data workloads.
- The legacy `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` tables are empty in the cluster — verified pre-merge before deletion.
- The reliability principles (WAL ceiling, connection ceiling, CPU ceiling, memory ceiling, client-side timeouts, idempotent / resumable) are non-negotiable and apply to every functional requirement in this spec.
- Phased rollout: Phase A bootstraps all 10 hubs from existing bronze in smallest-first order; Phase B builds the crosswalks and name indexes; Phase C rewrites silver enrichment models in priority order; Phase D wires structured-field linking starting with FAERS.

## Clarifications

### Session 2026-04-11 (round 3 — schema convention fix)

- Q: Which schemas should each hub live in? → A: After auditing `src/dk_data/sqlmesh/config.yaml`, the dk-data domain convention is **5 silver schemas**, not 3. The original /dk.auto run + parity work put `conditions` into `mol_silver` and patents/trademarks/designs into `ind_silver`, both of which violate the convention. Corrected layout: `mol_*` = molecules/drugs/compounds (molecules, drug_products, targets, companies); **`ind_*` = indication/disease/epidemiology (conditions)**; `hcs_*` = healthcare system/CMS/provider (providers, facilities); **`hcp_*` = healthcare professional/KOL/researcher (researchers — NEW hub)**; **`ip_*` = intellectual property (patents, trademarks, designs)**. This adds an 11th hub (`hcp_silver.researchers`) that the original run missed entirely because the source linkage doc enumerated only 10 entity types and did not include KOLs.
- Q: How do we distinguish providers from KOLs/researchers when the same physical person can be both? → A: Two separate hubs in two separate schemas. `hcs_silver.providers` is NPI-keyed (Medicare-billable regulatory entity, prescriber data); `hcp_silver.researchers` is ORCID/Scopus/PubMed-keyed (publication-derived KOL data). The same person gets a row in both, linked via `hcp_silver.researcher_provider_crosswalk` (FR-011b). This matches how commercial pharma intelligence platforms (Veeva OpenData, IQVIA OneKey, Definitive Healthcare, H1 Insights) split their data — prescriber data feeds market intelligence + Open Payments; KOL data feeds medical affairs + advisory board recruitment.
- Q: How are researchers populated without scraping ResearchGate / Google Scholar / paid Scopus? → A: PubMed `AuthorList` + `AffiliationInfo` provides the bulk; OpenAlex (`mol_bronze.openalex_ci`) provides ORCID + Scopus author ID + ROR institution xrefs. Bootstrap reads existing bronze only (FR-010, FR-036e). No new fetcher; no scraping; no LLM. Match confidence is two-tier per FR-013a/13b. ResearchGate / Google Scholar / commercial KOL DBs (Cortellis Speaker Data, H1 Insights) are deferred to a follow-up.

### Session 2026-04-11 (autonomous /dk.auto run)

- Q: Which entity hubs ship in v1 (this feature)? → A: All 10 hubs across mol_silver / hcs_silver / ind_silver (`molecules`, `drug_products` + `drug_product_ingredients`, `targets`, `conditions`, `companies`, `providers`, `facilities`, `patents`, `trademarks`, `designs`). Reasoning: the source linkage doc enumerates exactly these entity types; shipping a partial set would force consumers to wait on follow-up work and would leave silver enrichment models without targets to join to.
- Q: At what granularity does the drug product hub store rows? → A: SCD/SBD level (one row per RxNorm Semantic Clinical Drug). Reasoning: an NDC-level hub would force ~47 duplicate rows per generic clinical drug. Two-tier (SCD parent + NDC child) is overkill for v1 with no consumer use case requiring package-level distinction. SCD/SBD matches RxNorm's clinical-drug concept and how clinicians and pharmacists think about products. NDC moves to the crosswalk as `source = 'ndc'` rows.
- Q: What is the minimum confidence threshold for trigram fuzzy matches returned by the resolve functions? → A: Two-tier: 0.85 / 0.95. Resolve functions return matches at `pg_trgm` similarity ≥ 0.85 alongside the computed `confidence` value; matches below 0.85 return null. Gold-layer consumers and any clinical-grade silver join MUST filter on `confidence ≥ 0.95`. Reasoning: 0.85 is the standard `pg_trgm` "probably the same word" threshold; 0.95 is the standard "same word, possibly cased differently" threshold. Two-tier lets us use fuzzy matches for discovery without polluting clinical outputs.
- Q: What is the minimum schema for `meta.job_locks` and `meta.refresh_state`? → A: `meta.job_locks(name text PRIMARY KEY, locked_by text NOT NULL, locked_at timestamptz DEFAULT NOW(), expires_at timestamptz NOT NULL)`; `meta.refresh_state(procedure_name text PRIMARY KEY, last_chunk_position text NOT NULL, last_commit_at timestamptz DEFAULT NOW(), status text DEFAULT 'in_progress')`. Reasoning: matches the source reliability doc Section 3.1 Fix F4 + the resumability pattern. The implementer can add columns but cannot ship without these — pinning the minimum schema avoids implementation drift across multiple bootstrap procedures. Codified as FR-025/FR-026.
- Q: How is the SC-009 multi-tenant baseline measured? → A: 7-day rolling p95 of `application_name = 'behavior_labs'` and `application_name = 'litellm'` query latency from `pg_stat_activity`, captured immediately before the bootstrap kicks off. Reasoning: a fixed 7-day window is reproducible without `pg_stat_statements` (which is not enabled on this cluster); `application_name` is the only tenant attribution mechanism available.
- Q: What is the dedupe and conflict policy when a hub bootstrap re-encounters a `(source, identifier)` mapping to a different hub_id than its existing row? → A: `(source, identifier)` is `PRIMARY KEY` on every crosswalk; bootstrap inserts use `ON CONFLICT DO NOTHING`. Conflicts (existing row points at a different hub_id than the new resolution) MUST be logged to a new audit table `meta.linkage_conflicts` and MUST NOT silently overwrite. Reasoning: idempotence (FR-026) plus zero data loss; conflicts are rare but critical when they happen, and a silent overwrite would corrupt downstream joins. Codified as FR-026a.
