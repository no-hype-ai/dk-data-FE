# Feature Specification: Silver Hub Architecture & Reliability Rebuild

**Feature Branch**: `031-silver-hub-architecture`
**Created**: 2026-04-11
**Status**: Draft
**Input**: Rebuild the dk-data silver layer on top of an entity-resolution hub model so silver becomes a reliable single source of truth for downstream apps. Eliminate the inline cross-source linking patterns that crash the cluster, retain every column from upstream bronze sources, and constrain every silver/transform activity to fit inside the fixed CNPG cluster's WAL, CPU, memory, and connection ceilings.

**Source documents** (Cross-Project-Planning):
- `01-architecture-and-reliability/transformation-reliability-low-tech-solutions.md` — the 6 reliability principles, per-activity fixes, tray pattern, chunked PL/pgSQL procedures, BRIN indexing, PgBouncer integration, silver antipatterns, self-imposed budgets, app-side monitoring
- `01-architecture-and-reliability/silver-linkage-reference.md` — entity-linking patterns, source × entity × identifier matrix, hub + crosswalk + name-index architecture, resolve_*() function pattern, NLP extraction architecture, pragmatic bootstrap plan

**Related GitHub work**:
- Issue #253 — silver column retention audit (95 silver models drop bronze columns)
- 2026-04-10 incident — chembl_activities migration produced ~100 GB WAL in a single transaction, exceeded `max_wal_size = 4 GB`, triggered checkpoint storms, contributed to disk I/O exhaustion

---

## Clarifications

### Session 2026-04-11 (round 2)

- Q: How does the CI column-retention contract test discover each silver model's upstream bronze dependencies? → A: Use SQLMesh's built-in DAG introspection. The test loads a `sqlmesh.Context`, walks `context.dag.upstream(silver_model)` to find bronze dependencies, then reads `context.get_model(name).columns_to_types` for both sides. No live DB, no manifest file, no SQL comments to maintain. SQLMesh is the single source of truth — it cannot drift from the actual model code.
- Q: What's the granularity of `mol_silver.drug_products`, and what is the priority tree for `resolve_drug_product()`? → A: **SCD/SBD-level hub** (one row per RxNorm Semantic Clinical Drug / Semantic Branded Drug — e.g., one row for "Sildenafil 50 MG Oral Tablet", regardless of how many NDC packages exist for it). NDC is moved off the hub into the crosswalk; the linkage-doc schema's `UNIQUE (ndc)` constraint is dropped. The 11-step priority tree for `resolve_drug_product()` is: (1) NDC → crosswalk lookup; (2) RxCUI at TTY in (SCD, SBD, GPCK, BPCK) only — IN/BN RxCUIs return NULL with a hint to call `resolve_molecule()` instead; (3) BLA + product number; (4) NDA application + product number; (5) EMA product number; (6) CVX code; (7) structural hash `sha256(sorted(ingredient_unii) + dosage_form + route + strength_normalized)`; (8) brand + dosage_form + strength + route normalized; (9) generic + dosage_form + strength + route normalized; (10) brand alone; (11) trigram fuzzy on brand+generic (subject to FR-013a/13b confidence thresholds). Strength normalization to canonical unit (mg) is mandatory before comparing in steps 7–9.
- Q: What is the scope of `ind_silver` (the IP/intellectual property silver schema) in v1? → A: `ind_silver` gets its own hubs in v1. Three new hubs are added: `ind_silver.patents` (canonical patent entity), `ind_silver.trademarks` (canonical trademark entity), `ind_silver.designs` (canonical industrial design entity). v1 hub count is now **10** (was 7): the original `mol_silver.molecules` / `drug_products` / `targets` / `conditions` / `companies` plus `hcs_silver.providers` / `facilities` plus the three new `ind_silver` hubs. Each gets its own crosswalk, name index (for marks, titles, holders), and `resolve_*()` function. IP entities cross-link to the existing `mol_silver.companies` hub via assignee/owner/holder fields and to `mol_silver.molecules` via the existing Orange Book joining (FR-036a).

### Session 2026-04-11

- Q: Which entity hubs ship in v1 (this feature)? → A: 7 hubs initially scoped (mol_silver and hcs_silver only); expanded to **10** in round 2 after the `ind_silver` decision (see round-2 clarification below). Final v1 hub list: `mol_silver.molecules`, `mol_silver.drug_products` (+ `drug_product_ingredients`), `mol_silver.targets`, `mol_silver.conditions`, `mol_silver.companies`, `hcs_silver.providers`, `hcs_silver.facilities`, `ind_silver.patents`, `ind_silver.trademarks`, `ind_silver.designs`. The `hcs_silver.providers` bootstrap (~10M NPPES rows) and `mol_silver.companies` (degraded — no canonical ID) are accepted as part of v1 scope.
- Q: What exact column names count as "system columns" (exempt from the bronze→silver carry-forward contract)? → A: Exact list: `id`, `raw_id`, `ingested_at`, `request_timestamp`, `source`, `source_updated_at`, `processed_to_silver`, `processed_to_bronze`, `_loaded_at`, `raw_json`. Every other bronze column MUST carry forward.
- Q: When and how do we delete the legacy `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` models? → A: Delete both in this feature, in the same PR as the molecule hub bootstrap. The legacy tables are empty in the cluster, so consumer-migration risk is zero. The only safety check is a grep across `dk-data-FE`, `dk-flux`, `behavior-labs-web`, `xenon-repo`, and `dk-alchemy` for the literal table names; if any code references them by name (vs. doc text), warn the owner before merging. To preserve unnormalized display text that the legacy `molecule_aliases` carried, add a `display_name text` column to all name-index tables (`molecule_names`, `target_names`, etc.). The cross-reference provenance and conflict-detection use cases of `identifier_mappings` are intentionally dropped (not consumed today).
- Q: How do `resolve_*()` functions handle the trigram fuzzy fallback (Pattern D)? Is there a confidence threshold? → A: Two-tier. Resolve functions return matches with `pg_trgm` similarity ≥ 0.85 alongside the computed `confidence` value; matches below 0.85 return NULL. Gold-layer consumers (and any clinical-grade silver join) MUST filter on `confidence ≥ 0.95` to exclude probable fuzzy mismatches. This applies to every entity type's resolve function (molecules, drug_products, targets, conditions, companies, providers, facilities).
- Q: How are free-text sources (FAERS, ClinicalTrials, DailyMed, PubMed, EuropePMC, patents, SEC EDGAR, news) linked to entities in v1? Do we need LLM extraction? → A: **No LLM extraction in v1.** Source-API audit found that almost every "free text" field has a structured sibling that already does the entity resolution: openFDA `harmonization` arrays (UNII, RxCUI, NDC, substance_name) for FAERS and labels; ClinicalTrials.gov v2 `derivedSection.interventionMeshList` + `conditionMeshList`; PubMed `MeshHeadingList` + `ChemicalList`; Orange Book `application_number ↔ patent_number ↔ ingredient` for FDA-drug patents; static WHO INN regex for medical news. Cross-reference IDs (NCT, PMID, DOI, BLA) are pulled with simple regex over titles and abstracts. Coverage estimate: ~80–90% of what an LLM approach would deliver, at $0 API spend and zero model-drift / reproducibility risk. Genuinely prose-only cases (DailyMed `indications_and_usage`, non-FDA patent claim parsing, SEC EDGAR 10-K Business-section pipeline mentions, deal-flow extraction from 8-Ks) are explicitly **deferred** to a follow-up feature; if pipeline tracking becomes a real product need, licensing a commercial pharma pipeline DB (Cortellis / Adis Insight / GlobalData) is cheaper than building it. Story 5 is reframed accordingly; FR-033–036 are rewritten; SC-013 is replaced by a structured-coverage metric.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Silver is the complete, queryable source of truth (Priority: P1)

A data analyst querying `mol_silver.drugbank` to build a drug-interaction dashboard finds every column that exists in the bronze upstream — drug interactions, pathways, calculated properties, JSONB arrays, regulatory codes — already present in silver, alongside the entity-resolution columns (`molecule_id`, `drug_product_id`) that link the row to canonical entities. The analyst never has to reach back to bronze to find a missing field.

**Why this priority**: External applications and gold/mart models read **only** from silver and gold. If silver is missing data, the data is invisible to consumers and the medallion contract is broken. This is the reason the issue exists at all — fix it before anything else.

**Independent Test**: Query any silver table and confirm that every non-system column from its upstream bronze source(s) is present and populated. For multi-source aggregation models, also confirm that detail-level columns (per-DRG, per-APC, per-provider, per-ingredient) are accessible — not just aggregated totals.

**Acceptance Scenarios**:

1. **Given** a bronze table with columns `A, B, C, D` (none of which are system metadata), **When** the silver model that consumes it runs, **Then** the silver table contains `A, B, C, D` plus its entity-resolution columns (e.g., `molecule_id`).
2. **Given** a silver model that aggregates 9 upstream bronze tables, **When** consumers need detail-level fields (DRG codes, individual provider names, line-item financials), **Then** those fields are present in the same silver table — not aggregated away.
3. **Given** a bronze column of type JSONB (arrays, nested objects, raw payload), **When** carried to silver, **Then** the JSONB column is preserved as-is (not flattened, dropped, or stringified).
4. **Given** two bronze sources whose columns share a name (e.g., `max_phase` from ChEMBL and DrugBank), **When** both are merged into the same silver row, **Then** the columns are prefixed with the source name (`chembl_max_phase`, `drugbank_max_phase`) to avoid collisions.

---

### User Story 2 — Entity resolution lives in one place and uses indexes (Priority: P1)

When a silver enrichment model needs to know that ChEMBL `CHEMBL192`, DrugBank `DB00203`, PubChem `CID 5212`, FDA Orange Book `Viagra`, and the FAERS narrative reference "sildenafil citrate" all refer to the same molecule, it asks one canonical hub via a single indexed lookup — not by re-deriving the linkage with OR-joins, `LIKE '%name%'`, correlated subqueries, or `DISTINCT ON` over multi-way UNIONs. Adding a new identifier or changing disambiguation logic touches one PL/pgSQL function, not 8 silver models.

**Why this priority**: This is the architectural change that makes everything else possible. Without canonical hubs, every silver model continues to re-do entity resolution inline, the worst models (`adverse_events`, `bioactivity`, `molecule_publications`) continue to fail or never complete, and the column-retention work in Story 1 happens on top of a foundation that will keep collapsing. The hubs are also what allow the rebuild to fit inside the cluster's WAL ceiling — building a hub once is bounded; re-doing it inline forever is not.

**Independent Test**: After the molecule hub is bootstrapped, calling `mol_silver.resolve_molecule(p_chembl_id := 'CHEMBL192')` returns a stable integer in <10ms; the same call with `p_drugbank_id := 'DB00203'` returns the same integer; the same call with `p_inchi_key := 'BNRNXUUZRGQAQC-UHFFFAOYSA-N'` also returns the same integer. Joining a 25M-row bronze table to `mol_silver.molecule_identifiers` to attach `molecule_id` completes in under 60 seconds.

**Acceptance Scenarios**:

1. **Given** the molecule hub is populated, **When** any silver model needs `molecule_id` for a row, **Then** it obtains it via an indexed equi-join to `mol_silver.molecule_identifiers` or by calling `mol_silver.resolve_molecule()` — never via OR-joins, substring `LIKE`, correlated subqueries, or trigram similarity in the same WHERE clause as `=`.
2. **Given** a silver model previously implemented one of the antipatterns S1–S5 (OR-joins, `LIKE '%name%'`, correlated scalar subqueries, large `DISTINCT ON` over UNION ALL, `similarity()` mixed with `=` in OR), **When** the model is rewritten, **Then** none of those patterns appear in the new SQL.
3. **Given** a small molecule, a biologic (mAb without InChIKey), and a combination drug (RxNorm SCD with two ingredients), **When** each is resolved through the hubs, **Then** all three return correctly: the small molecule via InChIKey, the biologic via UNII or BLA number, the combination as one `drug_product_id` linked to two `molecule_id`s in `mol_silver.drug_product_ingredients`.
4. **Given** a free-text source (FAERS narrative, patent claim, news article) where the entity reference is buried in prose, **When** the row is enriched, **Then** entity extraction happens out-of-band into a `mol_raw.<source>_extracted` side table and silver joins to that side table by primary key — bronze and raw tables are not modified.

---

### User Story 3 — Transformation work fits inside the cluster's fixed budget (Priority: P1)

Every silver and transform activity respects the six reliability principles so that no single dk-data activity can crash, slow down, or starve the shared CNPG postgres pod that also hosts behavior_labs and litellm. The 2026-04-10 incident (single transaction producing ~100 GB of WAL on a cluster with `max_wal_size = 4 GB`) cannot recur because no transformation is allowed to generate more than ~1–2 GB of WAL in a single transaction.

**Why this priority**: The cluster is fixed (2 CPU / 4 GiB postgres pod, `shared_buffers=512MB`, `max_wal_size=4GB`, `max_connections=200`, single-node K3s, ZFS pool at 92% full, multi-tenant with BLAI and litellm, flaky barman-cloud archiver, `restart_after_crash=off`). We cannot ask Nick to change any of it. The hub bootstrap and silver rewrites only deliver value if they themselves don't repeat the 2026-04-10 failure.

**Independent Test**: Run the molecule hub bootstrap end-to-end during a low-traffic window. Verify via `pg_stat_wal` and `pg_stat_activity` that (a) no transaction generated more than 2 GB of WAL, (b) each chunk committed in under 30 seconds, (c) no BLAI or litellm query waited more than 1 second on a row lock during the run, (d) total WAL produced was under 5 GB across the full bootstrap, (e) the job is resumable: kill the pod mid-run, restart it, and it picks up at the last checkpoint without duplicating work.

**Acceptance Scenarios**:

1. **Given** any new or rewritten silver/transform model, **When** it runs against full production data, **Then** no single transaction produces more than ~2 GB of WAL (well under the 4 GB `max_wal_size` ceiling).
2. **Given** any dk-data database connection, **When** it is opened, **Then** it has `tcp_keepalives`, `statement_timeout`, `idle_in_transaction_session_timeout`, and `lock_timeout` set client-side (the server does not enforce them).
3. **Given** any long-running fetcher or transform pod, **When** it connects to postgres, **Then** it routes through `pgbouncer.infra.svc.cluster.local:5432` unless it requires session-level features (advisory locks, prepared statements, SQLMesh).
4. **Given** any dk-data CronJob, **When** it is killed by `activeDeadlineSeconds`, an OOM, a network blip, or a postgres restart, **Then** the next scheduled run picks up from the last persisted checkpoint without reprocessing already-committed work and without producing duplicate inserts.
5. **Given** the heaviest bronze and silver builds (chembl_activities, bindingdb, pubmed, europepmc, faers), **When** they execute, **Then** they use chunked PL/pgSQL procedures with mid-loop COMMITs (chunk size targeted at <50K rows / <200 MB WAL) and `pg_sleep(0.05)` between chunks to leave CPU breathing room for BLAI and litellm.
6. **Given** any 1st-of-month or April-15 stampede of CronJobs, **When** the schedule fires, **Then** the jobs are staggered across hours (or days) so the connection pool, CPU, and WAL ceilings are never all hit simultaneously.

---

### User Story 4 — The worst silver models are rewritten in priority order (Priority: P2)

The silver models that consumers depend on most — and that have historically been slowest, broken, or never-completing — are rewritten first to use indexed joins to the hubs. The rewrite preserves output semantics (validated by sample comparison) and unblocks the downstream models that depend on them.

**Why this priority**: P1 stories establish the foundation (column retention, hubs, reliability principles). This story is the visible payoff: the broken models start working. It is P2 only because it depends on P1 being in place; once hubs exist, each rewrite is straightforward.

**Independent Test**: Pick the highest-priority offender (`mol_silver.molecule_aliases`, then `mol_silver.adverse_events`, then `mol_silver.bioactivity`). For each, run the rewritten model against full production bronze, compare row counts and a 1% sample of output rows against the legacy model output, confirm runtime drops from "hours or never" to "under 10 minutes", and confirm WAL produced is under 1 GB per run.

**Acceptance Scenarios**:

1. **Given** the prioritized rewrite list (molecule_aliases → adverse_events → bioactivity → identifier_mappings → publications/articles → hcpcs_molecule_bridge → clinical_trials → drug_utilization → patents), **When** each model is rewritten, **Then** the new version completes in <10 minutes on production data and produces row counts within 1% of the legacy output (or with a documented reason for the delta).
2. **Given** a rewritten model whose legacy version contained antipatterns S1–S5, **When** code review runs, **Then** the new version contains zero instances of those antipatterns and joins exclusively to hub/crosswalk/name-index tables.
3. **Given** two legacy models that the hubs supersede outright (`molecule_aliases` → replaced by `mol_silver.molecule_names`; `identifier_mappings` → replaced by `mol_silver.molecule_identifiers`), **When** the hubs are stable and downstream consumers have migrated, **Then** the legacy models are deleted from the SQLMesh project (not left as no-op shells).

---

### User Story 5 — Free-text sources are linked via the structured fields the source APIs already provide (Priority: P3)

Sources we previously assumed needed NLP extraction (FAERS, ClinicalTrials.gov, DailyMed/openFDA labels, PubMed, EuropePMC, USPTO/EPO patents, SEC EDGAR, medical news/RSS) are linked to canonical hub entities by reading the **structured sibling fields** that the source APIs already populate alongside their prose. No LLM is called. No `_extracted` side tables are created for the structured-field cases.

**Why this priority**: Big payoff (FAERS adverse-event drug attribution, ClinicalTrials intervention linking, PubMed drug/condition tagging) at near-zero engineering cost — but it depends on the hubs (P1 Story 2) and the rewritten enrichment patterns (P2 Story 4) being in place first, so it lands after the foundation.

**Independent Test**: For FAERS specifically: parse `patient.drug[].openfda.unii[]`, `openfda.rxcui[]`, `openfda.substance_name[]`, and `patient.reaction[].reactionmeddrapt` from a 10K-row bronze sample; resolve each via `mol_silver.resolve_molecule()` and `mol_silver.resolve_condition()`; run the rewritten `mol_silver.adverse_events` model; verify ≥70% of rows have a non-null `molecule_id` and ≥85% have a non-null `condition_id`. No litellm-server call is made anywhere in the flow.

**Acceptance Scenarios**:

1. **Given** a FAERS bronze row with populated `openfda` arrays, **When** the rewritten `mol_silver.adverse_events` model runs, **Then** it resolves `molecule_id` from `openfda.unii` / `openfda.rxcui` / `openfda.substance_name` (in priority order) and `condition_id` directly from `reactionmeddrapt`.
2. **Given** a ClinicalTrials.gov bronze row, **When** the rewritten `mol_silver.clinical_trials` model runs, **Then** it reads `protocolSection.derivedSection.interventionMeshList` and `conditionMeshList` and joins to `mol_silver.molecules` / `mol_silver.conditions` via the existing MeSH crosswalk — never parses `interventionName` or `conditions` prose with an LLM.
3. **Given** a PubMed bronze row, **When** the rewritten `mol_silver.pubmed_articles` model runs, **Then** it reads `MeshHeadingList` and `ChemicalList` to attach drug and condition mentions, plus a `NCT\d{8}` regex over title+abstract to attach trial cross-references.
4. **Given** a USPTO patent bronze row corresponding to an FDA-approved drug, **When** the rewritten `mol_silver.patents` model runs, **Then** it joins to `mol_bronze.orange_book` on `(application_number, patent_number)` to obtain `molecule_id` — no patent-claims parsing.
5. **Given** a `mol_bronze.medical_news` row, **When** the news enrichment model runs, **Then** drug mentions are detected by a precompiled regex built from `mol_bronze.who_inn` (WHO INN list, ~10K names) — no LLM call.
6. **Given** a `mol_bronze.sec_edgar` row, **When** the company hub bootstrap runs, **Then** the row contributes a `mol_silver.companies` entry keyed on CIK + ticker + normalized company name; **no** prose parsing of 10-K Business section, 8-K events, or 10-Q MD&A is performed in v1. Crude company→drug linkage is delivered via fuzzy joins from `clinicaltrials.leadSponsor` and `fda_drugs.applicant_full_name` to the SEC company hub.

---

### Edge Cases

- **Biologics with no InChIKey** (mAbs, peptides, vaccines, gene therapies): the molecule hub allows `inchi_key` NULL and provides `sequence_hash`, `is_biologic`, and an alternative resolution priority that prefers UNII / BLA number / UniProt ID / WHO INN biologic stems / CVX code over structural keys.
- **Combination drugs** (RxNorm SCD/SBD, NDC `active_ingredients[]`, Orange Book semicolon-delimited ingredients): represented in `mol_silver.drug_products` (the product) and `mol_silver.drug_product_ingredients` (the many-to-many link to ingredient molecules). A FAERS report for "Combivent" maps to one `drug_product_id` and two `molecule_id`s.
- **Salt forms and stereoisomers** ("atorvastatin" vs "atorvastatin calcium"): different InChIKeys, both present in the hub, both linked to a common parent via `parent_molecule_id`. Clinical queries follow the parent pointer; chemical queries use the salt-specific ID.
- **Sources with no canonical identifier** (cms_magnet, hrsa, acc_tvc — facility name only; cms_open_payments — drug name only; sec_edgar applicants — company name only): resolution falls through to the name index (Pattern C) and finally to trigram fuzzy matching (Pattern D) with a confidence score; gold-layer consumers are warned to filter on confidence.
- **A bronze table is dropped or replaced**: silver models that depend on its columns must be updated in the same change, and the column-retention contract test (Story 1) must continue to pass.
- **A new bronze source is added**: the source must be wired into the appropriate hub bootstrap and crosswalk procedure before any silver model can join to it via the hubs.
- **The hub bootstrap is interrupted mid-run** (pod killed, postgres restart, network blip): the next run resumes from `meta.refresh_state` and produces no duplicate hub or crosswalk rows.
- **A silver rewrite produces a row count that differs from the legacy model by more than 1%**: the discrepancy must be explained (e.g., legacy model dropped rows due to OR-join failures; new model picks them up correctly) and documented in the PR before merging.
- **PgBouncer in transaction mode** breaks session-scoped advisory locks (`pg_try_advisory_lock`): the implementation uses `meta.job_locks` (a TTL-based persistent lock table) for any cross-pod coordination so locks survive transaction multiplexing.
- **A bronze row has empty `openfda` arrays / no MeSH headings / no Orange Book row**: the structured-field extraction returns NULL for the entity ID, the silver row is still written (carrying forward all bronze columns per FR-001), and the row is excluded from gold-layer joins that require a non-null entity ID. No retry — the source data is what it is. Gaps are logged so they can be quantified against SC-013.
- **A silver model needs `SET LOCAL work_mem` higher than 4 MB**: it must do so explicitly inside its own transaction and document the chosen value, because raising `work_mem` is per-session per-sort and a query with 10 sorts at `256MB` consumes 2.5 GB of RAM out of a 4 GiB pod budget.

---

## Requirements *(mandatory)*

### Functional Requirements

**Column retention (from User Story 1)**

- **FR-001**: Every silver SQLMesh model MUST include in its SELECT every non-system column present in its upstream bronze source(s), in addition to entity-resolution columns it adds. "System columns" are defined as exactly this list and no others: `id`, `raw_id`, `ingested_at`, `request_timestamp`, `source`, `source_updated_at`, `processed_to_silver`, `processed_to_bronze`, `_loaded_at`, `raw_json`.
- **FR-002**: When two upstream bronze columns share a name, the silver model MUST disambiguate by prefixing each with its source name (`chembl_max_phase`, `drugbank_max_phase`).
- **FR-003**: Bronze columns of type JSONB MUST be carried into silver as JSONB without flattening, stringification, or selective field extraction.
- **FR-004**: Silver aggregation models that summarize multiple bronze sources MUST also expose detail-level columns from those sources in the same silver table (no detail-only / summary-only split that hides fields).
- **FR-005**: A contract test MUST run in CI that, for each silver model, asserts that every non-system column of its upstream bronze source(s) is present in the silver model's column list. Upstream bronze dependencies MUST be discovered via SQLMesh's DAG introspection (`Context.dag.upstream(model_name)`); column lists MUST be obtained via `Context.get_model(name).columns_to_types`. The test MUST NOT require a live database connection and MUST NOT depend on a separately-maintained manifest or SQL comment annotation.

**Hub architecture (from User Story 2)**

- **FR-006**: The system MUST provide one canonical hub table per top-level entity type. v1 includes 10 hubs across three schemas: `mol_silver.molecules`, `mol_silver.drug_products`, `mol_silver.targets`, `mol_silver.conditions`, `mol_silver.companies`, `hcs_silver.providers`, `hcs_silver.facilities`, `ind_silver.patents`, `ind_silver.trademarks`, `ind_silver.designs`.
- **FR-007**: Each hub MUST have a synthetic `bigserial` primary key, `first_seen_at` and `last_updated_at` timestamps, and only canonical fields — no source-specific data.
- **FR-008**: The molecule hub MUST allow `inchi_key` to be NULL and MUST provide `sequence_hash`, `is_biologic`, and `parent_molecule_id` columns to handle biologics, salt forms, and stereoisomers.
- **FR-009**: The system MUST provide one identifier crosswalk table per entity type (`mol_silver.molecule_identifiers`, etc.), keyed on `(source, identifier)`, with each row pointing to one hub row.
- **FR-010**: The system MUST provide one normalized name index per entity type (`mol_silver.molecule_names`, etc.) keyed on `(normalized_name, hub_id)` with `name_kind`, `source`, `confidence`, and `display_name` (the original unnormalized spelling) columns. `display_name` preserves the raw text that the legacy `mol_silver.molecule_aliases` model carried, so consumers can still surface "Sildenafil (Viagra®)" instead of `sildenafilviagra`.
- **FR-011**: The system MUST provide a `mol_silver.drug_product_ingredients` many-to-many table linking products to molecule ingredients with `strength_value`, `strength_unit`, `is_active`, and `ingredient_order` columns.
- **FR-011a**: `mol_silver.drug_products` MUST be at **SCD/SBD-level granularity** — one row per RxNorm Semantic Clinical Drug or Semantic Branded Drug (e.g., one row for "Sildenafil 50 MG Oral Tablet", regardless of how many NDC packages exist for it). NDC is NOT a column on the hub; NDCs are stored as crosswalk rows in `mol_silver.drug_product_identifiers` with `source = 'ndc'`. The hub's only `UNIQUE` constraint on an external identifier is `(rxcui)` at SCD/SBD/GPCK/BPCK term type only.
- **FR-012**: The system MUST provide one `resolve_*()` PL/pgSQL function per entity type (`mol_silver.resolve_molecule`, etc.) that takes any combination of identifiers and a name as parameters, walks the type's resolution priority tree, and returns the canonical hub ID or NULL. Functions MUST be declared `STABLE PARALLEL SAFE`.
- **FR-013**: Each `resolve_*()` function MUST follow its entity type's documented priority tree:
  - **Small molecules** (`resolve_molecule`): InChIKey → ChEMBL → DrugBank → PubChem → UNII → CAS → RxCUI (IN/PIN only) → NDC → INN → normalized name → fuzzy
  - **Biologics** (`resolve_molecule`, when `is_biologic=true`): sequence hash → UniProt → ChEMBL biologic → DrugBank biotech → BLA → UNII → INN with biologic stems → CVX → IMGT → normalized name → fuzzy
  - **Drug products** (`resolve_drug_product`, SCD/SBD-level per FR-011a): NDC → RxCUI at TTY in (SCD, SBD, GPCK, BPCK) → BLA + product number → NDA application number + product number → EMA product number → CVX code → structural hash `sha256(sorted(ingredient_unii) + dosage_form + route + strength_normalized_mg)` → brand name + dosage_form + strength + route → generic name + dosage_form + strength + route → brand name alone → trigram fuzzy on brand+generic. RxCUIs at TTY in (IN, PIN, BN) MUST return NULL from `resolve_drug_product()` with a hint to call `resolve_molecule()` instead — these are ingredients or brand names, not products.
  - **Targets** (`resolve_target`): UniProt ID → ChEMBL target ID → HUGO gene symbol → Entrez Gene ID → Ensembl ID → sequence hash → PDB ID → normalized target name → fuzzy
  - **Conditions** (`resolve_condition`): ICD-11 → ICD-10 → MeSH descriptor → MedDRA PT → MedDRA LLT → ICD-10 chapter → normalized disease name → fuzzy
  - **Companies** (`resolve_company`): CIK → ticker → normalized company name (after stripping `Inc.`/`Corp.`/`Ltd.`/`AG`/`SA` etc.) → fuzzy. Note: degraded entity type — most matches will be at the name or fuzzy tier (FR-013b applies).
  - **Providers** (`resolve_provider`): NPI → PECOS ID → normalized (first_name + last_name + state + taxonomy) → fuzzy
  - **Facilities** (`resolve_facility`): CCN → NPI type-2 → NCDR facility ID → normalized (facility_name + city + state + ZIP) → fuzzy
  - **Patents** (`resolve_patent`): (jurisdiction, patent_number) → (jurisdiction, application_number) → (jurisdiction, publication_number) → PCT application number → normalized (title + first_assignee + filing_year) → fuzzy on title+assignee
  - **Trademarks** (`resolve_trademark`): (jurisdiction, registration_number) → (jurisdiction, serial_number) → WIPO Madrid international registration number → normalized (mark_text + sorted(nice_classes) + jurisdiction) → fuzzy on mark_text+owner
  - **Designs** (`resolve_design`): (jurisdiction, design_number) → WIPO Hague international design number → normalized (sorted(locarno_classes) + holder + filing_year) → fuzzy on holder
- **FR-013a**: The trigram fuzzy fallback (Pattern D) inside any `resolve_*()` function MUST return NULL for matches with `pg_trgm` similarity below 0.85. Matches at or above 0.85 MUST be returned together with the computed `confidence` value so callers can filter further.
- **FR-013b**: Gold-layer SQLMesh models, and any silver join treated as clinical-grade, MUST filter resolved entity rows on `confidence ≥ 0.95` so that fuzzy-only matches are excluded from clinical outputs.
- **FR-014**: All hub, crosswalk, and name-index tables MUST be indexed for the joins they support: PK indexes, hub-side btree indexes on canonical identifier columns, and GIN trigram indexes on `LOWER(canonical_name)` for fuzzy fallback.
- **FR-015**: All hub bootstrap procedures MUST read from the existing bronze tables and MUST NOT require any modification of `mol_raw`, `hcs_raw`, `ind_raw`, `mol_bronze`, `hcs_bronze`, or `ind_bronze` schemas or data.

**Silver rewrites (from User Stories 2 and 4)**

- **FR-016**: All silver models MUST obtain entity-resolution columns (`molecule_id`, `target_id`, `provider_id`, `facility_id`, `condition_id`, `drug_product_id`, etc.) by indexed equi-join to a hub crosswalk OR by calling the hub's `resolve_*()` function — never by inline cross-source linking.
- **FR-017**: Silver models MUST NOT contain antipattern S1 — OR-joins between two hub-eligible identifiers (`m.inchi_key = c.inchi_key OR LOWER(m.name) = LOWER(c.name)`).
- **FR-018**: Silver models MUST NOT contain antipattern S2 — leading-wildcard `LIKE '%' || name || '%'` substring matching against indexed columns.
- **FR-019**: Silver models MUST NOT contain antipattern S3 — correlated scalar subqueries in SELECT lists that re-execute per outer row.
- **FR-020**: Silver models MUST NOT contain antipattern S4 — global `DISTINCT ON` over multi-way `UNION ALL` of bronze tables.
- **FR-021**: Silver models MUST NOT contain antipattern S5 — `pg_trgm` `similarity()` combined with equality matchers in the same OR clause (which makes the trigram GIN index unusable).
- **FR-022**: The legacy `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` models MUST be deleted from the SQLMesh project in this feature, in the same PR that introduces the molecule hub bootstrap. Both tables are empty in the cluster today, so cutover risk is zero. The only required safety check is a literal-name grep across `dk-data-FE`, `dk-flux`, `behavior-labs-web`, `xenon-repo`, and `dk-alchemy`; any hit must be triaged with the owning code's author before merge.

**Reliability principles (from User Story 3)**

- **FR-023**: No single SQL transaction produced by a dk-data-FE workload MAY generate more than ~2 GB of WAL. Transformations that would exceed this MUST be chunked via PL/pgSQL procedures with mid-loop `COMMIT`s (target chunk size ≤50K rows / ≤200 MB WAL).
- **FR-024**: Every dk-data-FE database connection MUST be opened with `tcp_keepalives=1`, `keepalives_idle=60`, `keepalives_interval=10`, `keepalives_count=6`, `statement_timeout=600000`, `idle_in_transaction_session_timeout=300000`, and `lock_timeout=30000` set client-side (the server does not enforce them).
- **FR-025**: Every dk-data-FE database connection MUST set `application_name` to the pod name so it is identifiable in `pg_stat_activity` (the cluster has no `pg_stat_statements`).
- **FR-026**: All long-running fetcher and short-lived transform connections MUST route through `pgbouncer.infra.svc.cluster.local:5432` (env `POSTGRES_HOST`), with a separate `POSTGRES_HOST_DIRECT` env reserved for SQLMesh and PL/pgSQL workloads that require session-level features.
- **FR-027**: Cross-pod coordination MUST use a TTL-based `meta.job_locks` table rather than `pg_try_advisory_lock`, because PgBouncer transaction mode breaks session-scoped advisory locks.
- **FR-028**: Every dk-data-FE CronJob and bootstrap procedure MUST be idempotent and resumable: kill it mid-run and the next invocation picks up from the last persisted checkpoint (`meta.fetch_checkpoints`, `meta.refresh_state`) without duplicating work.
- **FR-029**: Any monthly stampede of CronJobs (e.g., `0 0 1 * *`) and the April-15 CMS PUF stampede MUST be staggered across hours or days so the connection pool, CPU, and WAL ceilings are not all hit simultaneously.
- **FR-030**: Heavy fetcher payloads (CMS PUFs >1 GB) MUST be downloaded with HTTP `Range` resume support so a network blip does not force a restart from byte 0.
- **FR-031**: The hub bootstrap MUST insert `pg_sleep(0.05)` between chunks to leave CPU breathing room for behavior_labs and litellm tenants on the shared CNPG pod.
- **FR-032**: Bootstrap and incremental refresh procedures MUST log per-chunk progress (rows processed, WAL bytes, elapsed seconds) so operators can see in real time whether a run is approaching the WAL ceiling.

**Structured-field entity linking (from User Story 5)**

- **FR-033**: Silver enrichment models for FAERS MUST resolve `molecule_id` by reading `patient.drug[].openfda.unii[]`, `patient.drug[].openfda.rxcui[]`, `patient.drug[].openfda.product_ndc[]`, and `patient.drug[].openfda.substance_name[]` (in that priority order) and calling `mol_silver.resolve_molecule()`. They MUST resolve `condition_id` directly from `patient.reaction[].reactionmeddrapt` via `mol_silver.resolve_condition()`. They MUST NOT call any LLM and MUST NOT parse the `medicinalproduct` or `narrative` prose fields.
- **FR-034**: Silver enrichment models for ClinicalTrials.gov MUST read `protocolSection.derivedSection.interventionMeshList[]` and `conditionMeshList[]` to obtain MeSH IDs, then resolve via `mol_silver.molecule_identifiers` (source `mesh`) and `mol_silver.condition_identifiers` (source `mesh`). They MUST NOT parse `interventionName` or `conditions` prose with an LLM.
- **FR-035**: Silver enrichment models for openFDA labels and DailyMed MUST resolve `molecule_id` and `drug_product_id` from the `openfda.unii[]`, `openfda.rxcui[]`, `openfda.product_ndc[]`, `openfda.application_number[]`, and `openfda.substance_name[]` arrays via `resolve_molecule()` and `resolve_drug_product()`. The `indications_and_usage` prose section is NOT parsed in v1; indication enrichment for these sources is deferred to a follow-up feature.
- **FR-036**: Silver enrichment models for PubMed and EuropePMC MUST read `MeshHeadingList[]` and `ChemicalList[]` (or the EuropePMC equivalents) to obtain drug and condition mentions, then resolve via the MeSH crosswalk in `molecule_identifiers` / `condition_identifiers`. Trial cross-references MUST be attached by running a `NCT\d{8}` regex over title and abstract; DOI and PMID cross-references MUST be attached by `10\.\d{4,9}/[-._;()/:A-Z0-9]+` (case-insensitive) and `PMID:?\s*\d+` regexes respectively. No LLM is called.
- **FR-036a**: Silver enrichment models for USPTO and EPO patents MUST attach `molecule_id` for FDA-approved drugs by joining `mol_bronze.orange_book` on `(application_number, patent_number)`. Patent claim prose is NOT parsed in v1; non-FDA-drug patent linkage is deferred to a follow-up feature that may ingest PatentsView, Lens.org, or similar pre-resolved sources.
- **FR-036b**: Silver enrichment models for `mol_bronze.medical_news` and journal RSS MUST detect drug mentions in titles via a precompiled regex built at startup from the `mol_bronze.who_inn` name list (~10K WHO INN entries). No LLM is called.
- **FR-036c**: The `mol_silver.companies` hub MUST be populated from `mol_bronze.sec_edgar` keyed on CIK + ticker + normalized company name. Crude company→drug linkage MUST be delivered via fuzzy trigram joins from `clinicaltrials.leadSponsor` and `fda_drugs.applicant_full_name` to `mol_silver.companies` (gated by FR-013a/FR-013b confidence thresholds). Prose parsing of 10-K, 10-Q, and 8-K filings is NOT performed in v1 and is deferred to a follow-up feature (see [data-kinetic/dk-data-FE#272](https://github.com/data-kinetic/dk-data-FE/issues/272)).
- **FR-036d**: To make FR-036c actually achievable, this feature MUST include a minimal fix to the existing `src/dk_data/ingestion/fetchers/sec_edgar.py` fetcher. The audit recorded in [data-kinetic/dk-data-FE#272](https://github.com/data-kinetic/dk-data-FE/issues/272) found that two of FR-036c's three required key fields (ticker, foreign-filer coverage) are not captured today and that the SIC filter is half-broken. The minimum fix required by this feature is: (1) add `20-F`, `6-K`, `40-F` to `FILING_TYPES` so foreign private issuers (Roche, Novartis, Sanofi, AstraZeneca, Bayer, Takeda, GSK, Daiichi Sankyo, etc.) are no longer invisible; (2) capture `ticker` for each filing via the SEC `data.sec.gov/submissions/CIK{padded}.json` endpoint with per-CIK caching, persist it through `mol_raw.sec_edgar` and `mol_bronze.sec_edgar`; (3) fix the SIC filter to use the same submissions endpoint as the source of truth instead of the unreliable inline `_sic` field. Bulk-download of XBRL Financial Statement Data Sets (Tier A), bulk filing-index replacement (Tier B), and full filing bodies in MinIO (Tier C) are out of scope for this feature and remain in the proposed `032-sec-edgar-bulk-rebuild` follow-up.

**CI / contract tests**

- **FR-037**: A CI job MUST validate every silver SQLMesh model against its bronze upstream(s) (discovered via SQLMesh DAG introspection per FR-005) and fail the build if any non-system bronze column is missing from the silver SELECT.
- **FR-038**: A CI job MUST grep silver model SQL for the antipattern signatures S1–S5 and fail the build on any match.
- **FR-039**: A CI job MUST validate that every dk-data-FE Python entry point uses `dk_data.ingestion.utils.database.build_dsn()` (or an equivalent helper) so connection-string safety knobs cannot be bypassed.

### Key Entities

- **Molecule hub** (`mol_silver.molecules`): one row per real-world molecule. Canonical fields only (`inchi_key`, `canonical_smiles`, `sequence_hash`, `is_biologic`, `parent_molecule_id`, `canonical_name`). Synthetic `bigserial` primary key. Allows NULL `inchi_key` for biologics.
- **Molecule identifier crosswalk** (`mol_silver.molecule_identifiers`): one row per `(source, identifier)` pair, with `molecule_id` foreign key. Indexed for sub-millisecond lookup.
- **Molecule name index** (`mol_silver.molecule_names`): one row per `(normalized_name, molecule_id)` pair with `name_kind` (canonical/generic/brand/IUPAC/synonym/INN/research_code), `source`, `confidence`, and `display_name` (the original unnormalized spelling preserved for UX).
- **Drug product hub** (`mol_silver.drug_products`): one row per RxNorm SCD/SBD-level clinical drug concept (per FR-011a) — e.g., one row for "Sildenafil 50 MG Oral Tablet" regardless of how many NDCs exist for it. Holds `product_id`, `rxcui` (UNIQUE at SCD/SBD/GPCK/BPCK term type), `bla_number`, `application_number`, `brand_name`, `generic_name`, `dosage_form`, `route`, `strength_normalized_mg`, `is_combination`, `is_biologic`, `is_biosimilar`, `reference_product_id`. NDC is NOT a hub column — it lives in `mol_silver.drug_product_identifiers` as a crosswalk row.
- **Drug product ingredients** (`mol_silver.drug_product_ingredients`): many-to-many link from `drug_products` to `molecules` with `strength_value`, `strength_unit`, `is_active`, `ingredient_order`.
- **Target hub** (`mol_silver.targets`) + identifiers + sequences: UniProt-anchored, with sequence-hash fallback for novel proteins.
- **Provider hub** (`hcs_silver.providers`) + identifiers: NPI-anchored, with PECOS ID, state license, DEA cross-references.
- **Facility hub** (`hcs_silver.facilities`) + identifiers: CCN-anchored, with NPI type-2 and NCDR fallbacks; trigram fuzzy fallback for sources without CCN (cms_magnet, hrsa, acc_tvc).
- **Condition hub** (`mol_silver.conditions`) + identifiers: ICD-anchored, with MeSH/MedDRA cross-references.
- **Company hub** (`mol_silver.companies`) + identifiers: best-effort name-anchored (CIK where available); flagged as the worst-supported entity type pending future LEI/DUNS/ROR ingestion.
- **Patent hub** (`ind_silver.patents`) + identifiers + name index: keyed on (jurisdiction, patent_number). Holds title, abstract, filing_date, grant_date, expiry_date, CPC codes, IPC codes, kind_code, status. Cross-references to `mol_silver.companies` via assignee, to `mol_silver.molecules` via Orange Book joining, and to `clinicaltrials` via patent-trial linkage where present.
- **Trademark hub** (`ind_silver.trademarks`) + identifiers + name index: keyed on (jurisdiction, registration_number) with serial_number as alt key. Holds mark_text, mark_type (word/figurative/3D/sound), Nice classes, registration_date, expiry_date, status, owner. Cross-references to `mol_silver.companies` via owner and (fuzzy) to `mol_silver.drug_products` via brand name matching.
- **Design hub** (`ind_silver.designs`) + identifiers + name index: keyed on (jurisdiction, design_number). Holds Locarno classes, filing_date, registration_date, holder, product_indication. Cross-references to `mol_silver.companies` via holder.
- **Resolve functions**: one PL/pgSQL function per entity type that accepts any combination of identifiers + a name and returns the canonical hub ID. The single point where resolution priority and disambiguation logic live.
- **Job locks** (`meta.job_locks`): TTL-based persistent lock table that survives PgBouncer transaction mode and auto-expires stale locks.
- **Cross-reference regex patterns**: precompiled at startup from `mol_bronze.who_inn` (drug names) and from static patterns (`NCT\d{8}`, `10\.\d{4,9}/[-._;()/:A-Z0-9]+`, `PMID:?\s*\d+`). No persistent table; the regex object lives in process memory and runs against PubMed / EuropePMC / news / RSS rows during the enrichment build. Replaces what would have been LLM-extracted side tables in the original Story 5.
- **Refresh state** (`meta.refresh_state`): per-procedure resumption checkpoint so any interrupted bootstrap or incremental refresh resumes at the last committed chunk.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** (column retention): 100% of silver SQLMesh models pass the CI contract test that asserts every non-system bronze column is carried forward. Coverage measured by counting `(silver_model, bronze_column)` pairs missing in silver vs. total such pairs.
- **SC-002** (hub coverage — molecules): After bootstrap, `mol_silver.molecule_identifiers` resolves at least 95% of distinct identifiers present in `mol_bronze.chembl_molecules`, `mol_bronze.drugbank`, `mol_bronze.pubchem`, `mol_bronze.rxnorm`, and `mol_bronze.fda_ndc` to a canonical `molecule_id`.
- **SC-003** (hub coverage — facilities): After bootstrap, `hcs_silver.facility_identifiers` resolves at least 90% of distinct CCNs present across the CMS hospital, quality, PUF, and PECOS bronze tables to a single canonical `facility_id`.
- **SC-004** (resolve function latency): `mol_silver.resolve_molecule()` returns in under 10ms p99 for any single-identifier lookup against indexed crosswalks.
- **SC-005** (silver model runtime): The 10 worst silver models (`molecule_aliases` → replaced; `adverse_events`, `bioactivity`, `molecule_publications`, `pubmed_articles`, `hcpcs_molecule_bridge`, `clinical_trials`, `drug_utilization`, `patents`, `identifier_mappings` → replaced) all complete in under 10 minutes on production data after rewrite.
- **SC-006** (WAL ceiling): No single transaction produced by any dk-data-FE workload exceeds 2 GB of WAL, measured via `pg_stat_wal` deltas during the run. Zero exceedances per week.
- **SC-007** (incident non-recurrence): The 2026-04-10 failure mode (single transaction generating >100 GB of WAL on `chembl_activities`) is impossible by design — all bronze and silver models that touch tables larger than 1M rows use chunked PL/pgSQL or are validated by an audit script that estimates WAL produced before merging.
- **SC-008** (hub bootstrap budget): The full hub bootstrap (all 10 hubs: molecules + drug_products + targets + providers + facilities + conditions + companies + patents + trademarks + designs) completes in under 105 minutes wall clock, produces under 7 GB of WAL total, and never holds a row lock for more than 1 second. (Budget increased from 90 min / 6 GB to absorb the three `ind_silver` hubs added in clarifications round 2; patents is the largest of the three at ~5M USPTO rows, trademarks ~12M, designs ~3M.)
- **SC-009** (multi-tenant impact): During hub bootstrap and silver rewrite runs, behavior_labs and litellm queries observe no more than a 10% p95 latency increase, measured by `application_name` filtering in `pg_stat_activity`.
- **SC-010** (resumability): Killing any dk-data-FE bootstrap or CronJob mid-run and restarting it completes with the same final state as a single uninterrupted run, with zero duplicate rows in target tables.
- **SC-011** (PgBouncer routing): At least 90% of dk-data-FE pod connections (excluding SQLMesh and PL/pgSQL procedure callers) terminate at PgBouncer rather than directly at the postgres primary, measured by `pg_stat_activity.client_addr`.
- **SC-012** (antipattern eradication): A repository-wide grep of `src/dk_data/sqlmesh/models/**/silver/*.sql` returns zero matches for the antipattern signatures S1–S5 after rewrite.
- **SC-013** (structured-field linkage coverage): After the rewritten enrichment models run against the full bronze backlog, the following coverage thresholds MUST be met using only structured-field parsing (no LLM): FAERS — ≥70% of rows have a non-null `molecule_id` and ≥85% have a non-null `condition_id` (resolved from `openfda.*` arrays and `reactionmeddrapt`); ClinicalTrials — ≥80% of trials have at least one `molecule_id` (from `interventionMeshList`) and ≥80% have at least one `condition_id` (from `conditionMeshList`); PubMed/EuropePMC — ≥75% of articles have at least one `molecule_id` or `condition_id` (from `MeshHeadingList`/`ChemicalList`); USPTO patents — 100% of patents in `mol_bronze.orange_book` have an `application_number` joinable to FDA-approved `molecule_id`; medical news — ≥40% of news items have at least one `molecule_id` from the WHO INN regex.
- **SC-014** (legacy model deletion): `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` are removed from the SQLMesh project in this feature, in the same PR as the molecule hub bootstrap. Both tables verified empty in the cluster pre-merge; consumer-repo grep complete with zero unresolved hits.
- **SC-015** (connection-string safety): 100% of dk-data-FE Python entry points obtain their DSN from a single `build_dsn()` helper that enforces FR-024 and FR-025; verified by CI.

---

## Assumptions

- The CNPG cluster, the postgres pod resource limits, the postgres configuration parameters, the PgBouncer deployment, the litellm-server deployment, the K3s topology, and the SeaweedFS / barman-cloud archiver are all out of scope for this feature. We adapt dk-data-FE to them; we do not change them. Anything that requires changing those is filed separately as "ask Nick" work and is not a blocker for this feature.
- The bronze layer is populated and uses `INCREMENTAL_BY_UNIQUE_KEY` model kinds (per merged PR #270). This feature does not modify bronze schemas, bronze model kinds, or fetcher behavior beyond the connection-string and idempotence fixes (FR-024 through FR-030).
- Re-ingestion is not an option. All hub and crosswalk construction reads from existing bronze data only.
- The `litellm-server` (penguin VMID 100) is NOT called by this feature. Source-API audit during clarifications showed that openFDA harmonization arrays, ClinicalTrials.gov `derivedSection.*MeshList`, PubMed `MeshHeadingList` + `ChemicalList`, and Orange Book already provide structured entity references for ~80–90% of the cases originally assumed to need LLM extraction. The remaining cases (DailyMed indication prose, non-FDA patent claims, SEC EDGAR 10-K Business sections, deal-flow extraction) are deferred to a follow-up feature; if pipeline tracking becomes a real product need, licensing a commercial pharma pipeline database (Cortellis, Adis Insight, BiomedTracker, GlobalData) is cheaper than building LLM extraction in-house.
- Phased rollout (per the source documents, scoped to all 10 hubs in v1 — see Clarifications): Phase A bootstraps all 10 hub tables (molecules, drug_products + ingredients, targets, conditions, companies, providers, facilities, patents, trademarks, designs) from existing bronze in priority of smallest-first to validate the chunked PL/pgSQL pattern before tackling the ~10M-row providers hub; Phase B builds the crosswalks and name indexes for all 10 hubs; Phase C rewrites silver enrichment models in priority order (now including `ind_silver` enrichment models that join to the new patent/trademark/design hubs); Phase D wires structured-field linking starting with FAERS. Each phase delivers a usable increment that is independently testable. The `hcs_silver.providers` hub (~10M NPPES rows) and `mol_silver.companies` (degraded, name-only resolution) are accepted as v1 scope.
- Trigram fuzzy matching is the last-resort fallback only — confidence scores are always assigned and gold-layer consumers filter on confidence.
- SNOMED CT, MONDO, OMIM, DUNS, LEI, ROR, JapicCTI, MedDRA hierarchy, and the IMGT antibody database are out of scope (not currently licensed or ingested) and will be added in follow-up features when sourcing is resolved.
- Future infrastructure changes that Nick may make (e.g., enabling `pg_stat_statements`, raising `max_wal_size`, adding HA, fixing the barman-cloud archiver) are improvements we will benefit from but are not required for this feature to ship.
