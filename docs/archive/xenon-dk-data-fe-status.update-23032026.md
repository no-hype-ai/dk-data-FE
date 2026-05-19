# xenon + dk-data-FE — System Status

---

## How dk-data-FE is designed to work

dk-data-FE is a data platform that ingests pharmaceutical data from ~43 external APIs and databases, transforms it through a medallion pipeline, and exposes it via PostgREST for consumption by xenon.

**Ingestion layer** — Python fetchers run on cron schedules (daily/weekly/monthly depending on source). Each fetcher hits an external API, stores the raw JSON response as a row in `mol_raw.<source>`. The raw table schema is uniform across all sources: `id, request_timestamp, api_endpoint, response_status, response_body (JSONB), processed_to_bronze`. A fetcher job writes one or more raw rows and returns a `job_id`. xenon can poll `GET /api/v1/data-platform/jobs/{job_id}` to know when it is done.

**Bronze layer (SQLMesh `INCREMENTAL_BY_TIME_RANGE`)** — SQLMesh reads `mol_raw.<source>` filtered by `request_timestamp` and extracts typed columns from the JSONB. Each model processes only newly-arrived raw rows since the last run (incremental by time). Output is `mol_bronze.<source>` with properly typed columns. Bronze is a staging layer — IDs are `gen_random_uuid()` since they don't need to be stable.

**Silver layer (SQLMesh `FULL` or `INCREMENTAL_BY_UNIQUE_KEY`)** — Silver models JOIN bronze against `mol_silver.molecules` to assign a `molecule_id` (UUID) to every row. This is the entity-linking step. The master molecule registry is `mol_silver.molecules`, built from ChEMBL using `md5(chembl_id)::uuid` as a deterministic, stable UUID. `FULL` kind models rebuild entirely on each run so that older rows get their `molecule_id` set when a new molecule enters the registry. `INCREMENTAL_BY_UNIQUE_KEY` models upsert on a natural key (e.g. `nct_id` for clinical trials) — because they scan all of bronze, newly onboarded molecules also get linked retroactively.

**Gold layer (SQLMesh `FULL`)** — Gold models aggregate silver into wide denormalized views for LLM consumption. Examples: `mol_gold.safety_signals` aggregates all FAERS adverse events per molecule into a single row with `total_reports`, `serious_reports`, and a `top_adverse_events` JSONB array. `mol_gold.competitive_landscape` identifies competing drugs in the same therapeutic area. Gold tables use TEXT `molecule_id` (not UUID FK) to remain decoupled.

**PostgREST** (port 3030) — exposes `mol_silver`, `mol_gold`, `ind_silver`, `hcp_gold`, `hcs_gold` schemas as REST endpoints. xenon queries these directly. PostgREST reads the DB schema at startup only — it must be restarted after any SQLMesh plan that adds or renames views.

**Entity linking strategy for biologics** — Small molecules have an `inchi_key` (structural fingerprint) that uniquely identifies them. Biologics (antibodies, ADCs) do not — they have `NULL inchi_key`. The pipeline uses `chembl_id` as the universal join key for all molecule types. DrugBank has a fallback: join on `LOWER(canonical_name) = LOWER(drug_name)` when `inchi_key IS NULL`.

**File-based sources (DrugBank, CMS USP)** — Two sources are not API-driven. DrugBank data comes from a licensed XML ZIP (`data/drugbank/drugbank_all_full_database.xml.zip`) bundled in the container image. CMS USP data comes from a bundled XLSX (`data/usp/usp_mmg_v9_alignment.xlsx`). Both are loaded at container startup if their target tables are empty, via a FastAPI `on_event("startup")` handler in `batch/api.py`.

---

## How xenon is designed to work

xenon is an AI-powered pharmaceutical assessment platform that produces a structured 17-section intelligence report from a molecule + indication pair.

**Assessment context** — A `(molecule_id, icd10_code)` pair stored in `xenon.assessment_contexts`. `molecule_id` must match a UUID in `mol_silver.molecules`. Each context can have multiple pipeline runs (retries, regeneration).

**Pipeline** — A BullMQ job (`generate-all`) processes one assessment context with 3 attempts and exponential backoff (3 min / 9 min):

1. **Data collection** — Fetches all registered sources from PostgREST in parallel. For sources with UUID `molecule_id`, queries `molecule_id=eq.{uuid}`. For array-typed columns, uses `cs.{uuid}` (PostgreSQL array-contains). For sources with no `molecule_id` column at all, fetches without a filter (`limit=1000`). Source semantics are defined in `apps/api/src/assessment/agents/data-registry.ts`.

2. **Sufficiency gating** — An LLM agent evaluates collected data and scores it. If sources are empty or low-quality, it flags them for enrichment and triggers dk-data-FE ingest jobs, then polls PostgREST until data arrives (120s timeout). A second LLM check gates whether generation should proceed. If still below threshold, throws `DATA_INSUFFICIENT` and BullMQ retries after a delay.

3. **Generation** — Three parallel batches: Batch 1 (ClinicalDataAgent + MarketIntelAgent), Batch 2 (StakeholderAgent), Batch 3 (SynthesisAgent). Each agent gets a filtered subset of collected data via `SECTION_DATA_MAP`. Sections are persisted to `xenon.generated_sections` immediately after each batch.

4. **Validation** — Zod schema validation, cross-section consistency check, hallucination stripping (competitor names not in competitive_landscape data are removed).

**Section scopes** — `molecule` (once per molecule, shared across indications — e.g. mechanism_of_action), `indication` (per indication — e.g. pivotal_trial_analysis, market_opportunity), `portfolio` (synthesises all indications — e.g. executive_summary, investment_thesis).

**Data registry** — `apps/api/src/assessment/agents/data-registry.ts` maps source keys to PostgREST paths, schemas, and query semantics. `buildNoMoleculeIdKeys()` identifies tables that have no `molecule_id` column and must not receive a molecule_id filter — sending one causes a PostgREST 400. `SECTION_DATA_MAP` in `section-data-map.ts` maps each section type to the source keys it requires.

---

## Current state — what is working

| Component | Status | Evidence |
|---|---|---|
| PostgREST | Working — no 400 errors | All schemas exposed; 490 relations; tested manually |
| xenon orchestrator query logic | Working | `NO_MOLECULE_ID_KEYS` prevents filter on no-molecule_id tables; `ema_regulatory_gold`/`cochrane_reviews_gold` path collision removed |
| job-trigger container | Stable | `init: true` prevents zombie processes |
| DrugBank — raw/bronze/silver load | Working | mol_raw.drugbank: 50,000 rows; mol_bronze.drugbank: 50,000 rows; mol_silver.drugbank: 50,000 rows |
| DrugBank — PostgREST access | Working | `Accept-Profile: mol_silver` on `/drugbank` returns data |
| DrugBank — startup load | Working | FastAPI startup handler loads from bundled ZIP if table empty |
| CMS USP | Working | hcs_raw.cms_usp: 11,016 rows; startup handler loads from bundled XLSX if empty |
| mol_silver.molecules | Working | ChEMBL-driven registry; deterministic UUIDs |
| mol_silver.clinical_trials | Working | Populated; INCREMENTAL_BY_UNIQUE_KEY |
| mol_silver.drug_labels | Working | Populated; INCREMENTAL_BY_UNIQUE_KEY |
| mol_gold.competitive_landscape | Working | arrayMoleculeId bug fixed (was using `cs.{}` on TEXT column) |
| xenon pipeline data collection | Working | PostgREST queries returning data across all registered sources |
| Section generation | Working | 16/17 section types generating |
| Hallucination stripping | Working | Competitor names not grounded in data are stripped post-generation |

---

## Current state — what is broken or not delivering expected value

**DrugBank pharmacological enrichment — delivering nothing for assessed molecules**

mol_silver.drugbank has 50,000 rows but they are low-quality. The XML parser in `fetchers/drugbank.py` uses `iterparse` and matches ALL `<drug>` elements at any nesting level, not just top-level drug entries. Drug targets, metabolites, and interaction references each embed nested `<drug>` stubs that have only `drugbank_id` and `name` — no description, indication, mechanism_of_action, pharmacodynamics, protein_binding, or any pharmacological fields. Of 50,000 parsed records, only 3,759 are unique DrugBank IDs; the remaining ~46,000 are content-empty duplicates from nested references.

Additionally, key assessed molecules — Durvalumab (DB14392), Atezolizumab, Dupilumab — are absent from the XML version currently bundled in the container image. Molecule linkage via canonical_name JOIN yields 11 matched rows (Adalimumab, Trastuzumab, Imatinib, Benzocaine, Nicergoline). The `mechanism_of_action` and `molecule_profile` sections have no DrugBank rows to draw from for the primary assessed molecules.

**mol_silver.adverse_events — linkage rate was ~17%, fix applied but unverified**

The ChEMBL synonym branch of `mol_silver.molecule_aliases` was calling `jsonb_array_elements_text()` on the `synonyms` column, which contains an array of objects. This serialized entire objects into strings (e.g. `syntypetradenamesynonymshumira...`) that never match a drug name in FAERS. Only molecules where canonical_name exactly matched a FAERS `drug_name` string got linked. The fix (`jsonb_array_elements()` + `->>'synonyms'` extraction) has been applied to the SQL model but the container has not been rebuilt and the production linkage rate has not been measured post-fix. `mol_gold.safety_signals` aggregates from `mol_silver.adverse_events` — all safety_signals gold rows were built from ~17% of available FAERS data. `safety_interpretation` section confidence was 0.52 as a result.

**mol_silver.side_effects — JOIN was silently returning nothing, fix applied but unverified**

`side_effects` links via PubChem CID: `mol_bronze.sider.pubchem_cid → mol_silver.pubchem.cid → mol_silver.molecules`. The model had `pc.pubchem_cid` in the JOIN but the column in `mol_silver.pubchem` is named `cid` (bigint). PostgreSQL raises no error — the LEFT JOIN simply never matched, leaving `molecule_id` NULL on every row. Fix applied (`pc.cid::TEXT`), container not rebuilt, production output unverified.

**mol_silver.protein_targets — has never successfully built**

The model referenced `t.target_class` from `mol_silver.targets`; the actual column name is `target_type`. This causes a PostgreSQL error on every SQLMesh plan run. `mol_silver.protein_targets` has 0 rows and has never populated. `mechanism_of_action` and `molecule_profile` sections lose structural protein data and IC50/binding affinity values as a result. Fix applied, container not rebuilt, build success unverified.

**INCREMENTAL_BY_UNIQUE_KEY idempotency — unverified**

`mol_silver.clinical_trials`, `mol_silver.drug_labels`, and `mol_silver.adverse_events` were converted from `FULL` to `INCREMENTAL_BY_UNIQUE_KEY`. For upsert to work correctly, the `id` column must produce the same UUID for the same logical row on every run — achieved via `md5(natural_key)::uuid`. If an older container build still uses `gen_random_uuid()`, every SQLMesh plan run inserts all rows as new duplicates. Row counts have not been monitored across consecutive runs to confirm idempotency.

**DATA_INSUFFICIENT failure rate — not re-measured since query fixes**

Before the PostgREST 400 fixes, ~69% of pipeline runs failed with `DATA_INSUFFICIENT`. A significant portion of that was caused by the orchestrator sending bad queries (400 errors returned as empty data, causing the sufficiency agent to score sources as absent). Now that 400 errors are eliminated, the failure rate should be lower, but it has not been measured on a fresh assessment run since the fixes were deployed.

**pivotal_trial_analysis confidence 0.17 — trial outcomes not yet exercised**

`populateTrialOutcomes()` has been implemented to parse `results_outcome_measures` from ClinicalTrials.gov and write per-endpoint data to `xenon.trial_outcomes`. This has not been exercised in a completed assessment run. The section was previously generating without any actual endpoint data (no hazard ratios, no response rates, no p-values) — relying entirely on drug label narrative text.

**SEC EDGAR — per-indication revenue breakdown structurally unavailable**

AstraZeneca files 20-F (foreign private issuer). The 20-F references revenue in an exhibit PDF rather than embedding numbers in the filing HTML. Even when the PDF is parsed, AZ reports total Imfinzi revenue — no per-indication breakdown (HCC vs. NSCLC vs. SCLC) exists in SEC filings. `financial_analysis` section for Durvalumab has no grounded revenue figures by indication.

**Competitor HTA and patent data — structural gap**

Competitor enrichment populates drug_labels, patent_exclusivities, and pivotal trials per competitor. It does not populate per-competitor HTA decisions or patent data. The competitive_positioning agent can compare trial data across competitors but cannot make grounded statements about competitor-specific HTA outcomes or patent cliffs.

---

## Needed actions

**Must fix before results are reliable:**

1. **Rebuild dk-data-FE job-trigger** after the three SQL model fixes (`adverse_events` synonym branch, `side_effects` JOIN, `protein_targets` column name) — none of these are live in the running container. After rebuild: run SQLMesh for each affected model, measure production linkage rates, confirm row counts are non-zero. Expected impact: `safety_interpretation` confidence from 0.52 → ~0.75+; `mechanism_of_action` from 0.48 → measurably higher.

2. **Fix DrugBank XML parser** — change `iterparse` to track nesting depth and only process top-level `<drug>` elements. This should yield ~14,000 clean unique drug entries with all pharmacological fields populated. Separately, verify whether the bundled XML version includes Durvalumab (DB14392) — if not, the XML file needs to be updated. Until this is fixed, DrugBank contributes nothing to assessments of the primary molecules.

3. **Re-measure DATA_INSUFFICIENT failure rate** — trigger a fresh assessment for Durvalumab/IMFINZI after the fixes above are deployed. Record which sources are still empty after the sufficiency enrichment cycle and whether the run completes. This is the most direct test of overall pipeline health.

**Needs verification (fixes already applied, not confirmed working):**

4. Confirm `mol_silver.adverse_events` linkage rate is >70% post-rebuild — run `SELECT COUNT(*) FILTER (WHERE molecule_id IS NOT NULL) / COUNT(*)::float FROM mol_silver.adverse_events`.

5. Confirm `mol_silver.side_effects` has linked rows post-rebuild.

6. Confirm `mol_silver.protein_targets` builds without error and has rows post-rebuild.

7. Confirm INCREMENTAL_BY_UNIQUE_KEY idempotency — check row counts in `mol_silver.clinical_trials` and `mol_silver.drug_labels` before and after a SQLMesh plan run to confirm counts are stable (not doubling).

8. Run a completed assessment and measure per-section confidence scores to establish a post-fix baseline — compare against the pre-fix scores (safety_interpretation 0.52, mechanism_of_action 0.48, molecule_profile 0.34, patient_journey 0.31, pivotal_trial_analysis 0.17).

**Lower priority / structural limitations:**

9. SEC EDGAR per-indication revenue: not solvable via filing parsing for AZ — would require product-level press releases or analyst report data sources.

10. Competitor HTA/patent data per-competitor: requires extending competitor enrichment to trigger HTA and patent ingest per competitor UUID, not just for the primary molecule.

11. imgt/npi/ttd sources: raw tables likely empty. Assess whether these sources are reachable and whether their data meaningfully improves any section.
