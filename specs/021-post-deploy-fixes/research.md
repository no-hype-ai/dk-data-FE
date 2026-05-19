# Research: Post-Deployment Fixes, SQL Audit & Silver Gap Closure

**Branch**: `021-post-deploy-fixes`

---

## Finding 1: Doppler Project Topology

**Decision**: `dk-data-applications/prd` is the single source of truth for all CronJob env vars.

**Root cause of EPO failure**: Keys were set in `dk-data-fe/prd` (wrong project) with `CHANGEME` placeholders in `dk-data-applications/prd`. Fixed by running:
```bash
doppler secrets set EPO_CONSUMER_KEY="..." EPO_CONSUMER_SECRET="..." \
  --project dk-data-applications --config prd
```

**Alternatives considered**: Adding a second `DopplerSecret` pointing to `dk-data-fe/prd` — rejected because it requires a second service token secret and adds operational complexity.

---

## Finding 2: Image Promotion and Self-Healing Pods

**Decision**: Failing pods running old image `prod-61e05d7` require no action — they self-heal.

**Pods affected**: `fetch-news` (weekly), `fetch-pubmed` (daily), `fetch-openalex-ci` (daily), `fetch-sec-edgar` (daily). All self-heal within 24 hours of prod promotion.

---

## Finding 3: DDInter Unreachability

**Decision**: Retire DDInter permanently. No recovery path.

`ddinter.scbdd.com` (Alibaba Cloud) TCP connection attempts timeout consistently since early March 2026. DDInter v2 equally unreachable.

**DDI coverage post-retirement**:
- `mol_bronze.drugbank_data.drug_interactions` — full DDI dataset from DrugBank XML (~17k drugs)
- `mol_bronze.bindingdb` — complementary binding affinity data

---

## Finding 4: USPTO API Registration Blocker

**Decision**: Track in issue #170, leave fetchers in `source_unavailable` skip mode.

USPTO account.uspto.gov requires ID.me verification with US government-issued ID + SSN. Registration is being done from outside the US. The USPTO legacy developer hub decommissions April 20, 2026.

**Resolution path**: (a) US-based team member registers, or (b) email APIhelp@uspto.gov for non-US registration assistance.

---

## Finding 5: SQLMesh HCS Pipeline Gap

**Decision**: Document gap; track separately. Out of scope for `021`.

The `cms-gold-refresh` CronJob runs `sqlmesh run hcs_gold.* mol_gold.*` daily but there are no HCS bronze or silver transform CronJobs. `job-initial-backfill` was never manually triggered on the cluster after PR #149 merged. HCS gold models produce empty results until upstream silver is populated.

---

## Finding 6: WHO ICD API Migration

**Decision**: Full fetcher rewrite. Both the ICD-10 URL and ICD-11 entity IDs were wrong.

**ICD-10**: `apps.who.int/classifications/icd10/browse/2019/en/JsonGetDescendants` returns HTTP 302 → HTML. Replaced with `id.who.int/icd/release/10/2019`. Same OAuth2 token as ICD-11.

**ICD-11 entity IDs**: Hardcoded IDs (e.g., `448895267`) returned 404. The root URL `id.who.int/icd/release/11/2024-01/mms` returns a JSON `child` array with all top-level chapter URLs — entity IDs can be extracted from these URLs dynamically. No hardcoded IDs needed.

**ICD-10 tree depth**: Old code only walked 2 levels. ICD-10 has 4 levels (chapter → block → 3-char → 4-char leaf). A recursive walker was added that follows `child` arrays at every node.

**Bronze column mismatch**: Both ICD-10 and ICD-11 return `title` as an object `{"@value": "…", "@language": "en"}`. The old bronze model tried to extract a flat `description` column that doesn't exist. Fixed to `response_body->'title'->>'@value'`.

---

## Finding 7: FULL Model `processed_to_silver` Anti-Pattern

**Decision**: Remove all `WHERE processed_to_silver = FALSE` filters from FULL models.

FULL models rebuild entirely on each run by design. A `processed_to_silver = FALSE` filter causes the model to return all rows on the first run (all rows have `FALSE`), then return zero rows on every subsequent run (all rows now have `TRUE`). This silently empties the table.

**Affected model confirmed**: `mol_silver.patent_exclusivities` — both the orange_book CTE and purple_book CTE had this filter.

**Rule going forward**: `processed_to_silver = FALSE` filters are only valid in INCREMENTAL models. FULL models must never use them.

---

## Finding 8: Grain Violation Pattern from Multi-Year Bronze Tables

**Decision**: Any silver model joining a bronze table whose grain includes `_source_year` must use `DISTINCT ON (silver_grain) ORDER BY silver_grain, _source_year DESC NULLS LAST`.

**Affected tables** (bronze grain includes `_source_year`):
- `hcs_bronze.cms_nppes` — grain `(npi, _source_year)`
- `hcs_bronze.cms_hospital_general_info` — grain `(facility_id, _source_year)`

**Silver models fixed**:
- `cms_pecos`, `cms_dmepos`, `cms_physician_puf_services` — join `cms_nppes`
- `cms_chow`, `cms_post_acute`, `cms_cost_reports_puf_lines`, `cms_hospital_affiliation` — join `cms_hospital_general_info`

**Pattern**: `ORDER BY …, _source_year DESC NULLS LAST` gives the most recent NPPES/HGI record when multiple years are present.

---

## Finding 9: Alias JOIN Fan-Out Pattern

**Decision**: All LEFT JOINs to `mol_silver.molecule_aliases` (or any table without a unique constraint on the JOIN key) must use `LEFT JOIN LATERAL (… LIMIT 1)` or `DISTINCT ON`.

**Root cause**: `molecule_aliases` grain is `(molecule_id, alias_name_normalized)`. Multiple rows can share the same `alias_name_normalized` when two molecules have the same alias (e.g., salt forms). An open LEFT JOIN fans out to one row per matching alias, multiplying rows in the calling model.

**Models fixed**: `ema_regulatory`, `imgt`, `cochrane_reviews`, `nice_hta`, `ttd`, `cms_ndc`, `cms_formulary`.

**New silver models designed with LATERAL from day one**: `cms_stabilis`, `cms_usp`, `ema_regulatory_docs`.

---

## Finding 10: `mol_silver.molecules` Column Inventory

`mol_silver.molecules` has **`canonical_name`** as the primary name column. Columns `inn_name` and `preferred_name` do not exist. Any model referencing these will fail at runtime.

**Models fixed**: `mol_silver.orange_book`, `mol_silver.healthcare_facilities` (hcs version).

---

## Finding 11: `identifier_mappings` Canonical `identifier_type` Values

Valid values populated by `mol_silver.identifier_mappings`:
`chembl_id`, `drugbank_id`, `pubchem_cid`, `cas_number`, `unii`, `uniprot_id`, `rxcui`, `ndc`

**Incorrect values found and fixed**:
- `pdb_ligand` → `pubchem_cid` (`mol_silver.protein_structures`)
- `uniprot` → `uniprot_id` (`mol_silver.proteins`)

---

## Finding 12: Dead-End Bronze Sources

**Decision**: All bronze sources must have at least one silver consumer. 7 sources had none.

**Linkage design principle**: Every silver model must use the least-ambiguous linkage strategy available, in priority order:
1. Exact canonical name match on `mol_silver.molecules`
2. Normalized alias match on `mol_silver.molecule_aliases` (LATERAL LIMIT 1)
3. First-token alias match (for multi-word INN variants like "bevacizumab alfa")
4. Identifier bridge (`identifier_mappings`, `hcpcs_molecule_bridge`)
5. Provider linkage: NPI → `cms_nppes`; CCN/facility_id → `cms_hospital_general_info`

All LATERAL subqueries use `ORDER BY molecule_id LIMIT 1` to ensure deterministic output when multiple aliases match.

---

## Doppler Keys Audit Summary

| Key | Value State | Action Taken |
|-----|-------------|--------------|
| `EPO_CONSUMER_KEY` | CHANGEME → real key | Updated via Doppler CLI |
| `EPO_CONSUMER_SECRET` | CHANGEME → real key | Updated via Doppler CLI |
| `USPTO_API_KEY` | CHANGEME (blocked) | Issue #170 |
| `USPTO_TSDR_API_KEY` | CHANGEME (blocked) | Issue #170 |
| `DRUGBANK_API_KEY` | Empty (intentional) | No action — XML seed covers it |
| `EUIPO_API_KEY` | Set ✅ | — |
| `EUIPO_SECRET_KEY` | Set ✅ | — |
| `NCBI_API_KEY` | Set ✅ | — |
| `OPENALEX_API_KEY` | Set ✅ | — |
| `WHO_ICD_CLIENT_ID` | Set ✅ | — |
| `WHO_ICD_CLIENT_SECRET` | Set ✅ | — |
| `LITELLM_API_KEY` | Set ✅ | — |
| `LITELLM_BASE_URL` | Set ✅ | — |
| `DATABASE_URL` | Set ✅ | — |
