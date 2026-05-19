# Resolve Function Contracts

The 10 `resolve_*()` functions are the only public surface this feature exposes (besides the silver tables themselves, which are exposed via PostgREST and are governed by the existing API surface). Each function follows the same shape:

- Declared `LANGUAGE plpgsql STABLE PARALLEL SAFE`
- Takes positional or named parameters for every supported identifier + a name field
- Returns the canonical hub ID (`bigint`) or `NULL` if no tier produces a match at or above the confidence threshold
- Walks the priority tree top-to-bottom and returns the first non-null match
- Trigram fuzzy fallback (final tier) returns NULL below similarity 0.85

## `mol_silver.resolve_molecule`

```sql
CREATE OR REPLACE FUNCTION mol_silver.resolve_molecule(
    p_inchi_key   text DEFAULT NULL,
    p_chembl_id   text DEFAULT NULL,
    p_drugbank_id text DEFAULT NULL,
    p_pubchem_cid text DEFAULT NULL,
    p_unii        text DEFAULT NULL,
    p_cas_number  text DEFAULT NULL,
    p_rxcui       text DEFAULT NULL,            -- IN/PIN tier RxCUIs only; SCD/SBD/GPCK go to resolve_drug_product
    p_ndc         text DEFAULT NULL,
    p_inn         text DEFAULT NULL,
    p_name        text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree** (FR-013, source linkage doc small molecule + biologic sections):
1. `inchi_key` → `mol_silver.molecules.inchi_key`
2. `chembl_id` → crosswalk source `chembl`
3. `drugbank_id` → crosswalk source `drugbank`
4. `pubchem_cid` → crosswalk source `pubchem`
5. `unii` → crosswalk source `unii`
6. `cas_number` → crosswalk source `cas`
7. `rxcui` → crosswalk source `rxnorm` (IN/PIN term type only — SCD/SBD/GPCK callers should use `resolve_drug_product`)
8. `ndc` → crosswalk source `ndc`
9. `inn` → crosswalk source `inn`
10. `name` → `molecule_names.normalized_name` (priority by `confidence DESC, name_kind`)
11. trigram fuzzy on `LOWER(canonical_name) gin_trgm_ops` ≥ 0.85

For biologics (`is_biologic = true` rows), the same function applies — the InChIKey tier silently no-ops (NULL `inchi_key`), and the function falls through to UNII / BLA-equivalent / INN / CVX / IMGT tiers via the crosswalk sources.

## `mol_silver.resolve_drug_product`

```sql
CREATE OR REPLACE FUNCTION mol_silver.resolve_drug_product(
    p_ndc                 text DEFAULT NULL,
    p_rxcui               text DEFAULT NULL,    -- SCD/SBD/GPCK/BPCK only — IN/PIN/BN return NULL
    p_bla_number          text DEFAULT NULL,
    p_bla_product_number  text DEFAULT NULL,
    p_application_number  text DEFAULT NULL,
    p_application_product_number text DEFAULT NULL,
    p_ema_product_number  text DEFAULT NULL,
    p_cvx_code            text DEFAULT NULL,
    p_ingredients_hash    text DEFAULT NULL,    -- sha256(sorted(ingredient_unii) + dosage_form + route + strength_normalized_mg)
    p_brand_name          text DEFAULT NULL,
    p_generic_name        text DEFAULT NULL,
    p_dosage_form         text DEFAULT NULL,
    p_strength_normalized_mg numeric DEFAULT NULL,
    p_route               text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree** (FR-013, 11 steps):
1. `ndc` → crosswalk source `ndc`
2. `rxcui` → `mol_silver.drug_products.rxcui` UNIQUE — but ONLY if RxCUI term type is in (SCD, SBD, GPCK, BPCK). IN/PIN/BN RxCUIs return NULL with a postgres NOTICE recommending the caller use `resolve_molecule` instead.
3. `(bla_number, bla_product_number)` → hub direct join
4. `(application_number, application_product_number)` → hub direct join
5. `ema_product_number` → hub direct join
6. `cvx_code` → hub direct join
7. `ingredients_hash` → hub computed via `mol_silver.drug_product_ingredients` join (Pattern A structural)
8. `(brand_name, dosage_form, strength_normalized_mg, route)` normalized → hub direct join
9. `(generic_name, dosage_form, strength_normalized_mg, route)` normalized → hub direct join
10. `brand_name` alone → hub direct join
11. trigram fuzzy on `brand_name + ' ' + generic_name` ≥ 0.85

## `mol_silver.resolve_target`

```sql
CREATE OR REPLACE FUNCTION mol_silver.resolve_target(
    p_uniprot_id        text DEFAULT NULL,
    p_chembl_target_id  text DEFAULT NULL,
    p_gene_symbol       text DEFAULT NULL,    -- HUGO
    p_entrez_id         text DEFAULT NULL,
    p_ensembl_id        text DEFAULT NULL,
    p_sequence_hash     text DEFAULT NULL,
    p_pdb_id            text DEFAULT NULL,
    p_name              text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `uniprot_id` → `mol_silver.targets.uniprot_id`
2. `chembl_target_id` → crosswalk source `chembl_target`
3. `gene_symbol` (HUGO) → crosswalk source `hugo`
4. `entrez_id` → crosswalk source `entrez`
5. `ensembl_id` → crosswalk source `ensembl`
6. `sequence_hash` → `mol_silver.targets.sequence_hash` (Pattern A — for novel proteins not yet in UniProt)
7. `pdb_id` → crosswalk source `pdb` (PDB→UniProt indirection)
8. `name` (normalized) → `mol_silver.target_names.normalized_name`
9. trigram fuzzy on canonical_name ≥ 0.85

## `ind_silver.resolve_condition`

```sql
CREATE OR REPLACE FUNCTION ind_silver.resolve_condition(
    p_icd11      text DEFAULT NULL,
    p_icd10      text DEFAULT NULL,
    p_mesh       text DEFAULT NULL,    -- MeSH descriptor ID
    p_meddra_pt  text DEFAULT NULL,
    p_meddra_llt text DEFAULT NULL,
    p_name       text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `icd11` → `ind_silver.conditions.icd11_code`
2. `icd10` → `ind_silver.conditions.icd10_code`
3. `mesh` → `ind_silver.conditions.mesh_descriptor_id`
4. `meddra_pt` → `ind_silver.conditions.meddra_pt`
5. `meddra_llt` → crosswalk source `meddra_llt` (LLT→PT indirection)
6. ICD-10 chapter (derived therapeutic area bucket) → crosswalk source `icd10_chapter`
7. `name` (normalized) → `ind_silver.condition_names.normalized_name`
8. trigram fuzzy on canonical_name ≥ 0.85

**Note**: SNOMED CT, MONDO, OMIM are out of scope (Gap 6, deferred items §1).

## `mol_silver.resolve_company`

```sql
CREATE OR REPLACE FUNCTION mol_silver.resolve_company(
    p_cik          text DEFAULT NULL,
    p_ticker       text DEFAULT NULL,
    p_name         text DEFAULT NULL,
    p_country      text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `cik` → `mol_silver.companies.cik`
2. `ticker` → `mol_silver.companies.ticker`
3. `name` normalized (after stripping `Inc.`/`Corp.`/`Corporation`/`Ltd.`/`Limited`/`LLC`/`AG`/`SA`/`SARL`/`PLC`/`GmbH`/`KGaA`/`KK`/`Co., Ltd.`/`Pty Ltd` and similar suffixes) → `mol_silver.companies.canonical_name`
4. trigram fuzzy on `canonical_name` (after the same suffix stripping) ≥ 0.85

**Most matches will fall through to the name or fuzzy tier.** Gold consumers MUST filter `confidence ≥ 0.95` (FR-013b). This is the worst-supported entity type — see deferred items Gap 5.

## `hcs_silver.resolve_provider`

```sql
CREATE OR REPLACE FUNCTION hcs_silver.resolve_provider(
    p_npi              text DEFAULT NULL,
    p_pecos_id         text DEFAULT NULL,
    p_first_name       text DEFAULT NULL,
    p_last_name        text DEFAULT NULL,
    p_state            text DEFAULT NULL,
    p_taxonomy_code    text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `npi` → `hcs_silver.providers.npi` (canonical US ID)
2. `pecos_id` → `hcs_silver.providers.pecos_id` (Medicare enrollment)
3. State medical license number → crosswalk source `state_license` (NOT YET CAPTURED — see deferred items §3 #8)
4. DEA number → crosswalk source `dea` (NOT YET CAPTURED)
5. Normalized `(lower(first_name) || ' ' || lower(last_name) || ' ' || state || ' ' || taxonomy_code)` → composite key lookup against `hcs_silver.providers (last_name, first_name, state, primary_taxonomy_code)`
6. trigram fuzzy on the composite ≥ 0.85

**Use case**: cms_open_payments rows that have first_name+last_name+state but no NPI fall through to step 5/6.

## `hcs_silver.resolve_facility`

```sql
CREATE OR REPLACE FUNCTION hcs_silver.resolve_facility(
    p_ccn          text DEFAULT NULL,
    p_npi_type2    text DEFAULT NULL,
    p_ncdr_id      text DEFAULT NULL,
    p_facility_name text DEFAULT NULL,
    p_city         text DEFAULT NULL,
    p_state        text DEFAULT NULL,
    p_zip          text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `ccn` → `hcs_silver.facilities.ccn` (canonical for Medicare-enrolled facilities)
2. `npi_type2` → `hcs_silver.facilities.npi_type2` (organizational NPI from NPPES)
3. `ncdr_id` → `hcs_silver.facilities.ncdr_id` (cardiac registries)
4. Normalized `(lower(facility_name) || ' ' || lower(city) || ' ' || state || ' ' || zip)` → composite key lookup
5. trigram fuzzy on `facility_name + ' ' + city + ' ' + state` ≥ 0.85

**Use case**: cms_magnet, hrsa, acc_tvc rows that have facility name + state but no CCN fall through to step 5.

## `hcp_silver.resolve_researcher`

```sql
CREATE OR REPLACE FUNCTION hcp_silver.resolve_researcher(
    p_orcid              text DEFAULT NULL,
    p_scopus_author_id   text DEFAULT NULL,
    p_pubmed_signature   text DEFAULT NULL,    -- normalized 'lower(lastname)_lower(firstinitial)'
    p_researchgate_id    text DEFAULT NULL,
    p_google_scholar_id  text DEFAULT NULL,
    p_full_name          text DEFAULT NULL,
    p_institution        text DEFAULT NULL,
    p_country            text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `orcid` → `hcp_silver.researchers.orcid_id` UNIQUE — the canonical international researcher identifier
2. `scopus_author_id` → `hcp_silver.researchers.scopus_author_id` UNIQUE
3. `pubmed_signature` → `hcp_silver.researchers.pubmed_author_signature` (lookup the normalized `lower(lastname)_lower(firstinitial)` against the precomputed signature column)
4. `researchgate_id` → crosswalk source `researchgate`
5. `google_scholar_id` → crosswalk source `google_scholar`
6. Normalized `(lower(full_name) || ' ' || lower(institution) || ' ' || country)` → composite name+institution lookup
7. Trigram fuzzy on `full_name + ' ' + institution` ≥ 0.85

**Use case**: PubMed `AuthorList` rows have `LastName + ForeName + Initials + AffiliationInfo` for each author. The resolver builds the pubmed_signature from `(lastname, firstinitial)` and matches it against the hub. If multiple authors share the same lastname+firstinitial, the institution is the disambiguator. If institution doesn't match cleanly, the row falls through to fuzzy and gold consumers must filter on `confidence ≥ 0.95`.

**Note**: This is a NEW hub for the dk-data-FE platform. The existing repo has no `hcp_silver.researchers` model — feature 031 (speckit) and the original dk auto run both missed it because the source linkage doc enumerated only 10 entity types. The dk-data SQLMesh config already declares the `hcp_silver` schema; this feature adds the first model that lives there.

## `ip_silver.resolve_patent`

```sql
CREATE OR REPLACE FUNCTION ip_silver.resolve_patent(
    p_jurisdiction          text DEFAULT NULL,
    p_patent_number         text DEFAULT NULL,
    p_application_number    text DEFAULT NULL,
    p_publication_number    text DEFAULT NULL,
    p_pct_application_number text DEFAULT NULL,
    p_title                 text DEFAULT NULL,
    p_first_assignee        text DEFAULT NULL,
    p_filing_year           int  DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `(jurisdiction, patent_number)` → `ip_silver.patents` UNIQUE constraint
2. `(jurisdiction, application_number)` → `ip_silver.patents.application_number`
3. `(jurisdiction, publication_number)` → `ip_silver.patents.publication_number` (EPO-style)
4. `pct_application_number` → crosswalk source `pct`
5. Normalized `(lower(title) || ' ' || lower(first_assignee) || ' ' || filing_year::text)` → name index lookup
6. trigram fuzzy on `title + ' ' + first_assignee` ≥ 0.85

**Note**: Drug-patent linkage (which patent protects which FDA drug) is NOT in the priority tree above — it lives in the silver enrichment join via Orange Book (FR-034).

## `ip_silver.resolve_trademark`

```sql
CREATE OR REPLACE FUNCTION ip_silver.resolve_trademark(
    p_jurisdiction          text DEFAULT NULL,
    p_registration_number   text DEFAULT NULL,
    p_serial_number         text DEFAULT NULL,
    p_wipo_madrid_number    text DEFAULT NULL,
    p_mark_text             text DEFAULT NULL,
    p_nice_classes          int[] DEFAULT NULL,
    p_owner                 text DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `(jurisdiction, registration_number)` → `ip_silver.trademarks` UNIQUE
2. `(jurisdiction, serial_number)` → `ip_silver.trademarks.serial_number` (pre-registration)
3. `wipo_madrid_number` → `ip_silver.trademarks.wipo_madrid_number` (Madrid international)
4. Normalized `(lower(mark_text) || ' ' || array_to_string(sort(nice_classes), ',') || ' ' || jurisdiction)` → composite lookup
5. trigram fuzzy on `mark_text + ' ' + owner` ≥ 0.85

**Cross-link**: trademarks with mark_text matching a `mol_silver.drug_products.brand_name` should fuzzy-link to drug products via a separate enrichment model (subject to FR-013b confidence threshold).

## `ip_silver.resolve_design`

```sql
CREATE OR REPLACE FUNCTION ip_silver.resolve_design(
    p_jurisdiction        text DEFAULT NULL,
    p_design_number       text DEFAULT NULL,
    p_wipo_hague_number   text DEFAULT NULL,
    p_locarno_classes     int[] DEFAULT NULL,
    p_holder              text DEFAULT NULL,
    p_filing_year         int  DEFAULT NULL
) RETURNS bigint
LANGUAGE plpgsql STABLE PARALLEL SAFE
```

**Priority tree**:
1. `(jurisdiction, design_number)` → `ip_silver.designs` UNIQUE
2. `wipo_hague_number` → `ip_silver.designs.wipo_hague_number` (Hague international)
3. Normalized `(array_to_string(sort(locarno_classes), ',') || ' ' || lower(holder) || ' ' || filing_year::text)` → composite lookup
4. trigram fuzzy on `holder` ≥ 0.85

**Note**: Image-hash matching (Pattern A for designs) is NOT in v1 — would require image embedding infrastructure.

---

## Caller contract

Every silver enrichment model that needs an entity ID MUST call the relevant `resolve_*()` function or join to the corresponding `*_identifiers` crosswalk by `(source, identifier)`. Inline cross-source linkage is forbidden by FR-014–FR-019.

Example caller pattern (replaces antipattern S1 from FR-015):

```sql
-- Old (forbidden — OR-join on hub-eligible identifiers)
SELECT b.activity_id,
       (SELECT m.molecule_id FROM mol_bronze.chembl_molecules c
        JOIN mol_silver.molecules m ON ((m.inchi_key = c.inchi_key)
                                     OR (LOWER(m.canonical_name)=LOWER(c.pref_name)))
        WHERE c.chembl_id = b.chembl_id LIMIT 1) AS molecule_id
FROM mol_bronze.chembl_activities b;

-- New (indexed equi-join via crosswalks; uses resolve_molecule for the few rows that need name fallback)
SELECT b.activity_id,
       COALESCE(mi_chembl.molecule_id, mi_drugbank.molecule_id) AS molecule_id,
       ti.target_id,
       b.activity_value, b.activity_unit
FROM mol_bronze.chembl_activities b
LEFT JOIN mol_silver.molecule_identifiers mi_chembl
       ON mi_chembl.source = 'chembl' AND mi_chembl.identifier = b.chembl_id
LEFT JOIN mol_silver.molecule_identifiers mi_drugbank
       ON mi_drugbank.source = 'drugbank' AND mi_drugbank.identifier = b.drugbank_id
LEFT JOIN mol_silver.target_identifiers ti
       ON ti.source = 'chembl_target' AND ti.identifier = b.target_chembl_id;
```
