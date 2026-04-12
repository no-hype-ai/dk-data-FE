# Data Model — Silver Medallion Rebuild

All schemas are PostgreSQL 16.4. Synthetic primary keys are `bigserial`. Every hub gets PK + identifier crosswalk + name index + resolve function. Schema layout matches the dk-data domain convention in `src/dk_data/sqlmesh/config.yaml`.

## Schema overview

| Schema | Domain | Status | Tables added / changed by this feature |
|---|---|---|---|
| `mol_silver` | Molecule / drug / compound | Existing — extended | `molecules`, `molecule_identifiers`, `molecule_names`, `drug_products`, `drug_product_identifiers`, `drug_product_names`, `drug_product_ingredients`, `targets`, `target_identifiers`, `target_names`, `target_sequences`, `companies`, `company_identifiers`, `company_names`. Removed (migrated to `ip_silver`): `patents`, `trademarks`, `patent_exclusivities`, `trademark_status_changes`, `euipo_designs` (renamed → `ip_silver.designs`) |
| `ind_silver` | Indication / disease / epidemiology | Existing — extended | `conditions`, `condition_identifiers`, `condition_names` |
| `hcs_silver` | Healthcare system / CMS / provider | Existing — extended | `providers`, `provider_identifiers`, `provider_names`, `facilities`, `facility_identifiers`, `facility_names` |
| `hcp_silver` | Healthcare professional / KOL / researcher | Existing schema (declared in `config.yaml`) but no models — populated by this feature | `researchers`, `researcher_identifiers`, `researcher_names`, `researcher_provider_crosswalk`, `researcher_publications`, `researcher_affiliations` |
| `ip_raw` | Intellectual property — raw | **NEW SCHEMA** (FR-006a/c) | All IP-related raw tables — moved from `mol_raw`: `uspto_patents`, `uspto_ci`, `uspto_trademarks`, `epo_patents`, `euipo_trademarks`, `euipo_designs`, `trademark_status_history` |
| `ip_bronze` | Intellectual property — bronze | **NEW SCHEMA** (FR-006a/d) | All IP-related bronze models — moved from `mol_bronze`: `uspto_patents`, `uspto_ci`, `uspto_trademarks`, `epo_patents`, `euipo_trademarks`, `euipo_designs`, `trademark_status_history` |
| `ip_silver` | Intellectual property — silver | **NEW SCHEMA** (FR-006a/e) | NEW hub-architecture: `patents`, `patent_identifiers`, `patent_names`, `trademarks`, `trademark_identifiers`, `trademark_names`, `designs`, `design_identifiers`, `design_names`. Migrated legacy: `patent_exclusivities`, `trademark_status_changes` |
| `ip_gold` | Intellectual property — gold | **NEW SCHEMA** (FR-006a/f) | Empty in v1; reserved for follow-up gold models like `patent_landscape`, `trademark_freedom_to_operate` |
| `meta` | Metadata + observability | Existing — extended | `job_locks`, `refresh_state`, `linkage_conflicts`, `transform_runs`, `slow_query_log`, `wal_usage`, `activity_log`, `wal_status`, `job_runs` |

## Hub tables

### `mol_silver.molecules`

```sql
CREATE TABLE mol_silver.molecules (
    molecule_id bigserial PRIMARY KEY,
    inchi_key text UNIQUE,                       -- nullable for biologics
    canonical_smiles text,
    sequence_hash text,                          -- SHA-256 of amino acid sequence (biologics)
    is_biologic boolean DEFAULT false,
    parent_molecule_id bigint REFERENCES mol_silver.molecules(molecule_id),
    canonical_name text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON mol_silver.molecules (canonical_name);
CREATE INDEX ON mol_silver.molecules USING GIN (LOWER(canonical_name) gin_trgm_ops);
CREATE INDEX ON mol_silver.molecules (parent_molecule_id) WHERE parent_molecule_id IS NOT NULL;
CREATE INDEX ON mol_silver.molecules (sequence_hash) WHERE sequence_hash IS NOT NULL;
```

### `mol_silver.drug_products` (SCD/SBD level — FR-012)

```sql
CREATE TABLE mol_silver.drug_products (
    product_id bigserial PRIMARY KEY,
    rxcui text UNIQUE,                           -- RxNorm at TTY in (SCD, SBD, GPCK, BPCK) only
    bla_number text,
    bla_product_number text,
    application_number text,                     -- Drugs@FDA NDA application
    application_product_number text,
    ema_product_number text,
    cvx_code text,
    brand_name text,
    generic_name text,
    dosage_form text,
    route text,
    strength_normalized_mg numeric,
    is_combination boolean DEFAULT false,
    is_biologic boolean DEFAULT false,
    is_biosimilar boolean DEFAULT false,
    reference_product_id bigint REFERENCES mol_silver.drug_products(product_id),
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON mol_silver.drug_products (brand_name);
CREATE INDEX ON mol_silver.drug_products (generic_name);
CREATE INDEX ON mol_silver.drug_products (reference_product_id) WHERE reference_product_id IS NOT NULL;
```

NDC is NOT a hub column — lives in `mol_silver.drug_product_identifiers` as `(source = 'ndc', identifier = '0069-4200-30')` rows.

### `mol_silver.drug_product_ingredients`

```sql
CREATE TABLE mol_silver.drug_product_ingredients (
    product_id bigint REFERENCES mol_silver.drug_products(product_id),
    molecule_id bigint REFERENCES mol_silver.molecules(molecule_id),
    strength_value numeric,
    strength_unit text,
    is_active boolean DEFAULT true,
    ingredient_order int,
    PRIMARY KEY (product_id, molecule_id)
);
CREATE INDEX ON mol_silver.drug_product_ingredients (molecule_id);
```

### `mol_silver.targets`

```sql
CREATE TABLE mol_silver.targets (
    target_id bigserial PRIMARY KEY,
    uniprot_id text UNIQUE,
    sequence_hash text,
    canonical_name text,
    target_type text,                            -- 'protein', 'enzyme', 'receptor', etc.
    organism text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON mol_silver.targets (canonical_name);
CREATE INDEX ON mol_silver.targets (sequence_hash) WHERE sequence_hash IS NOT NULL;
```

### `ind_silver.conditions`

```sql
CREATE TABLE ind_silver.conditions (
    condition_id bigserial PRIMARY KEY,
    icd11_code text,
    icd10_code text,
    mesh_descriptor_id text,
    meddra_pt text,
    canonical_name text,
    therapeutic_area text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW(),
    UNIQUE (icd11_code),
    UNIQUE (icd10_code),
    UNIQUE (mesh_descriptor_id),
    UNIQUE (meddra_pt)
);
```

### `mol_silver.companies`

```sql
CREATE TABLE mol_silver.companies (
    company_id bigserial PRIMARY KEY,
    cik text UNIQUE,
    ticker text,
    canonical_name text NOT NULL,                -- normalized: 'pfizer' not 'Pfizer Inc.'
    country text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON mol_silver.companies (canonical_name);
CREATE INDEX ON mol_silver.companies USING GIN (LOWER(canonical_name) gin_trgm_ops);
```

### `hcp_silver.researchers` (FR-011b)

```sql
CREATE TABLE hcp_silver.researchers (
    researcher_id bigserial PRIMARY KEY,
    orcid_id text UNIQUE,                        -- ORCID iD: 0000-0002-1825-0097
    scopus_author_id text UNIQUE,                -- Scopus author identifier
    pubmed_author_signature text,                -- normalized "lastname_firstinitial" composite for PubMed first/last author matching
    researchgate_id text,
    google_scholar_id text,
    canonical_full_name text NOT NULL,           -- "Smith, John A." normalized
    primary_affiliation_institution text,
    primary_affiliation_country text,
    h_index int,                                 -- if available from Scopus / Google Scholar
    first_publication_year int,
    last_publication_year int,
    is_active boolean DEFAULT true,              -- has published in the last 5 years
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON hcp_silver.researchers (canonical_full_name);
CREATE INDEX ON hcp_silver.researchers USING GIN (LOWER(canonical_full_name) gin_trgm_ops);
CREATE INDEX ON hcp_silver.researchers (primary_affiliation_institution);
CREATE INDEX ON hcp_silver.researchers (last_publication_year DESC);
```

### `hcp_silver.researcher_provider_crosswalk`

```sql
CREATE TABLE hcp_silver.researcher_provider_crosswalk (
    researcher_id bigint NOT NULL REFERENCES hcp_silver.researchers(researcher_id),
    provider_id bigint NOT NULL REFERENCES hcs_silver.providers(provider_id),
    confidence numeric NOT NULL,                 -- match confidence — typically fuzzy via name+state+institution
    matched_via text NOT NULL,                   -- 'orcid', 'name+institution+state', 'name+publication_address', etc.
    first_seen_at timestamptz DEFAULT NOW(),
    PRIMARY KEY (researcher_id, provider_id)
);
CREATE INDEX ON hcp_silver.researcher_provider_crosswalk (provider_id);
```

The same physical person — a practicing oncologist who also publishes in NEJM — gets a row in `hcs_silver.providers` (NPI-keyed) AND a row in `hcp_silver.researchers` (ORCID-keyed). The crosswalk links them. Match confidence is computed from name + institution + state agreement; gold consumers MUST filter `confidence ≥ 0.95` per FR-013.

### `hcp_silver.researcher_publications`

```sql
CREATE TABLE hcp_silver.researcher_publications (
    researcher_id bigint NOT NULL REFERENCES hcp_silver.researchers(researcher_id),
    pmid text,                                   -- PubMed ID
    doi text,                                    -- Digital Object Identifier
    pmcid text,                                  -- PubMed Central ID
    publication_year int,
    author_position text,                        -- 'first', 'middle', 'last', 'corresponding'
    journal_name text,
    PRIMARY KEY (researcher_id, COALESCE(pmid, doi, pmcid))
);
CREATE INDEX ON hcp_silver.researcher_publications (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX ON hcp_silver.researcher_publications (doi) WHERE doi IS NOT NULL;
CREATE INDEX ON hcp_silver.researcher_publications (publication_year DESC);
```

This is the bridge table from researchers to PubMed publications. Cross-references to `mol_silver.molecules` (via PubMed `ChemicalList`) and `ind_silver.conditions` (via PubMed `MeshHeadingList`) are derivable by joining `researcher_publications.pmid` to the existing `mol_silver.pubmed_articles` enrichment model.

### `hcp_silver.researcher_affiliations`

```sql
CREATE TABLE hcp_silver.researcher_affiliations (
    researcher_id bigint NOT NULL REFERENCES hcp_silver.researchers(researcher_id),
    institution_name text NOT NULL,              -- normalized institution name
    institution_country text,
    affiliation_type text,                       -- 'academic', 'industry', 'government', 'hospital', 'unknown'
    company_id bigint REFERENCES mol_silver.companies(company_id),  -- populated when affiliation resolves to industry org
    first_year int,
    last_year int,
    is_current boolean DEFAULT false,
    PRIMARY KEY (researcher_id, institution_name, COALESCE(first_year, 0))
);
CREATE INDEX ON hcp_silver.researcher_affiliations (institution_name);
CREATE INDEX ON hcp_silver.researcher_affiliations (company_id) WHERE company_id IS NOT NULL;
```

When `affiliation_type = 'industry'`, the `company_id` foreign key resolves to `mol_silver.companies` — this is the bridge that lets us answer "which researchers have industry affiliations and with which companies?" without needing a separate KOL-influence-graph data source.

### `hcs_silver.providers`

```sql
CREATE TABLE hcs_silver.providers (
    provider_id bigserial PRIMARY KEY,
    npi text UNIQUE,                             -- canonical
    pecos_id text UNIQUE,
    first_name text,
    last_name text,
    middle_name text,
    credential text,
    primary_taxonomy_code text,
    primary_specialty text,
    state text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON hcs_silver.providers (last_name, first_name, state);
```

### `hcs_silver.facilities`

```sql
CREATE TABLE hcs_silver.facilities (
    facility_id bigserial PRIMARY KEY,
    ccn text UNIQUE,                             -- canonical
    npi_type2 text UNIQUE,
    ncdr_id text UNIQUE,
    facility_name text NOT NULL,
    city text,
    state text,
    zip text,
    ownership_type text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON hcs_silver.facilities (facility_name);
CREATE INDEX ON hcs_silver.facilities (state, city);
```

### `ip_silver.patents`

```sql
CREATE TABLE ip_silver.patents (
    patent_id bigserial PRIMARY KEY,
    jurisdiction text NOT NULL,                  -- 'US', 'EP', 'WO', 'JP', etc.
    patent_number text,
    application_number text,
    publication_number text,
    pct_application_number text,
    title text,
    abstract text,
    filing_date date,
    grant_date date,
    expiry_date date,
    cpc_codes text[],
    ipc_codes text[],
    kind_code text,
    status text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW(),
    UNIQUE (jurisdiction, patent_number),
    UNIQUE (jurisdiction, application_number)
);
CREATE INDEX ON ip_silver.patents (filing_date);
CREATE INDEX ON ip_silver.patents USING GIN (cpc_codes);
```

### `ip_silver.trademarks`

```sql
CREATE TABLE ip_silver.trademarks (
    trademark_id bigserial PRIMARY KEY,
    jurisdiction text NOT NULL,
    registration_number text,
    serial_number text,
    wipo_madrid_number text,
    mark_text text NOT NULL,
    mark_type text,                              -- 'word', 'figurative', '3D', 'sound'
    nice_classes int[],
    registration_date date,
    expiry_date date,
    status text,
    owner_company_id bigint REFERENCES mol_silver.companies(company_id),
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW(),
    UNIQUE (jurisdiction, registration_number),
    UNIQUE (jurisdiction, serial_number)
);
CREATE INDEX ON ip_silver.trademarks (mark_text);
CREATE INDEX ON ip_silver.trademarks USING GIN (LOWER(mark_text) gin_trgm_ops);
CREATE INDEX ON ip_silver.trademarks USING GIN (nice_classes);
CREATE INDEX ON ip_silver.trademarks (owner_company_id);
```

### `ip_silver.designs`

```sql
CREATE TABLE ip_silver.designs (
    design_id bigserial PRIMARY KEY,
    jurisdiction text NOT NULL,
    design_number text,
    wipo_hague_number text,
    locarno_classes int[],
    filing_date date,
    registration_date date,
    holder_company_id bigint REFERENCES mol_silver.companies(company_id),
    product_indication text,
    first_seen_at timestamptz DEFAULT NOW(),
    last_updated_at timestamptz DEFAULT NOW(),
    UNIQUE (jurisdiction, design_number)
);
CREATE INDEX ON ip_silver.designs (holder_company_id);
CREATE INDEX ON ip_silver.designs USING GIN (locarno_classes);
```

## Identifier crosswalks (one per hub — same shape)

```sql
CREATE TABLE mol_silver.molecule_identifiers (
    source text NOT NULL,                        -- 'chembl', 'drugbank', 'pubchem', 'rxnorm', 'unii', 'cas', 'inn', 'ndc'
    identifier text NOT NULL,
    molecule_id bigint NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    is_primary boolean DEFAULT false,
    first_seen_at timestamptz DEFAULT NOW(),
    PRIMARY KEY (source, identifier)
);
CREATE INDEX ON mol_silver.molecule_identifiers (molecule_id);
```

The same shape applies to: `mol_silver.drug_product_identifiers`, `target_identifiers`, `condition_identifiers`, `company_identifiers`, `hcs_silver.provider_identifiers`, `facility_identifiers`, `ip_silver.patent_identifiers`, `trademark_identifiers`, `design_identifiers`.

## Name indexes (one per hub — same shape)

```sql
CREATE TABLE mol_silver.molecule_names (
    normalized_name text NOT NULL,
    molecule_id bigint NOT NULL REFERENCES mol_silver.molecules(molecule_id),
    name_kind text NOT NULL,                     -- 'canonical', 'generic', 'brand', 'iupac', 'synonym', 'inn', 'research_code'
    source text NOT NULL,
    confidence numeric DEFAULT 1.0,
    display_name text,                           -- original unnormalized spelling
    first_seen_at timestamptz DEFAULT NOW(),
    PRIMARY KEY (normalized_name, molecule_id, source)
);
CREATE INDEX ON mol_silver.molecule_names (molecule_id);
CREATE INDEX ON mol_silver.molecule_names USING GIN (normalized_name gin_trgm_ops);
```

Same shape applies to all 9 other name index tables.

## Meta tables

### `meta.job_locks` (FR-025)

```sql
CREATE TABLE meta.job_locks (
    name text PRIMARY KEY,
    locked_by text NOT NULL,
    locked_at timestamptz DEFAULT NOW(),
    expires_at timestamptz NOT NULL
);
```

### `meta.refresh_state` (FR-026)

```sql
CREATE TABLE meta.refresh_state (
    procedure_name text PRIMARY KEY,
    last_chunk_position text NOT NULL,
    last_commit_at timestamptz DEFAULT NOW(),
    status text DEFAULT 'in_progress'            -- 'in_progress', 'completed', 'failed'
);
```

### `meta.linkage_conflicts` (FR-026a)

```sql
CREATE TABLE meta.linkage_conflicts (
    conflict_id bigserial PRIMARY KEY,
    detected_at timestamptz DEFAULT NOW(),
    source text NOT NULL,
    identifier text NOT NULL,
    existing_hub_id bigint NOT NULL,
    new_hub_id bigint NOT NULL,
    procedure_name text NOT NULL
);
CREATE INDEX ON meta.linkage_conflicts (detected_at);
CREATE INDEX ON meta.linkage_conflicts (procedure_name);
```

### `meta.transform_runs` (FR-021 accounting — see research Topic 5)

```sql
CREATE TABLE meta.transform_runs (
    run_id bigserial PRIMARY KEY,
    procedure_name text NOT NULL,
    chunk_position text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    rows_processed bigint NOT NULL,
    wal_bytes bigint NOT NULL
);
CREATE INDEX ON meta.transform_runs (procedure_name, started_at);
CREATE INDEX ON meta.transform_runs (wal_bytes) WHERE wal_bytes > 500000000;  -- alerts on >500 MB chunks (FR-021 ceiling)
```

### `meta.slow_query_log` (FR-041 — pg_stat_statements substitute)

```sql
CREATE TABLE meta.slow_query_log (
    id bigserial PRIMARY KEY,
    label text NOT NULL,
    elapsed_ms numeric NOT NULL,
    pod_name text NOT NULL,
    logged_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON meta.slow_query_log (label, logged_at DESC);
CREATE INDEX ON meta.slow_query_log (logged_at DESC);
```

Populated by the `dk_data.ingestion.utils.db_timing.timed_query()` Python context manager. Default slow threshold is 1000 ms. Aggregation queries grouped by `label` give us per-operation latency profiles without needing `pg_stat_statements`.

### `meta.wal_usage` (FR-042 — per-CronJob WAL accounting)

```sql
CREATE TABLE meta.wal_usage (
    id bigserial PRIMARY KEY,
    job_name text NOT NULL,
    wal_mb numeric NOT NULL,
    logged_at timestamptz DEFAULT NOW()
);
CREATE INDEX ON meta.wal_usage (job_name, logged_at DESC);
CREATE INDEX ON meta.wal_usage (wal_mb) WHERE wal_mb > 5000;  -- alerts on >5 GB CronJob runs (FR-021a ceiling)
```

Populated at the end of every fetcher and transform CronJob run by bracketing the run with `pg_current_wal_lsn() - '0/0'::pg_lsn`. Distinct from `meta.transform_runs`, which is per-chunk inside a procedure; `meta.wal_usage` is per-CronJob-run.

### `meta.activity_log` (FR-043 — pg_stat_activity snapshots)

```sql
CREATE TABLE meta.activity_log (
    snapshot_at timestamptz NOT NULL,
    datname text,
    usename text,
    application_name text,
    state text,
    wait_event_type text,
    wait_event text,
    query_start timestamptz,
    xact_start timestamptz,
    query_age_seconds numeric,
    query text
);
CREATE INDEX ON meta.activity_log (snapshot_at);
CREATE INDEX ON meta.activity_log (application_name, snapshot_at);
CREATE INDEX ON meta.activity_log (xact_start) WHERE xact_start IS NOT NULL;
```

Populated every 60 seconds by a CronJob that captures non-idle `pg_stat_activity` rows for `datname = 'dk_data'` with the first 500 chars of the query text. Enables post-incident "what was running at time T" investigations.

### `meta.wal_status` (FR-044 — WAL accumulation tracking)

```sql
CREATE TABLE meta.wal_status (
    snapshot_at timestamptz PRIMARY KEY,
    wal_files int NOT NULL,
    wal_size_bytes bigint NOT NULL,
    max_active_replication_lag_bytes bigint,
    max_inactive_replication_lag_bytes bigint
);
```

Populated every 5 minutes via:

```sql
INSERT INTO meta.wal_status
SELECT
    NOW(),
    (SELECT count(*) FROM pg_ls_waldir()),
    (SELECT sum(size) FROM pg_ls_waldir()),
    (SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
     FROM pg_replication_slots WHERE active),
    (SELECT max(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))
     FROM pg_replication_slots WHERE NOT active);
```

Alerts on `wal_size_bytes > 20 GB` (5x `max_wal_size`, indicates accumulation) and `max_inactive_replication_lag_bytes > 1 GB` (dead replication slot).

### `meta.job_runs` (FR-059 — in-flight job tracking)

```sql
CREATE TABLE meta.job_runs (
    id bigserial PRIMARY KEY,
    job_name text NOT NULL,
    started_at timestamptz DEFAULT NOW(),
    completed_at timestamptz,
    status text DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed', 'killed')),
    pod_name text,
    error_message text,
    rows_processed bigint
);
CREATE INDEX ON meta.job_runs (job_name, started_at DESC);
CREATE INDEX ON meta.job_runs (status) WHERE status = 'running';
```

Populated by the `job-trigger` service on every fetcher / transform invocation. Distinct from `meta.refresh_state` (per-procedure, used for resumability) and `meta.transform_runs` (per-chunk WAL accounting).

## Resolve function signatures (full implementations in `contracts/`)

| Function | Returns | Priority tree |
|---|---|---|
| `mol_silver.resolve_molecule(p_inchi_key, p_chembl_id, p_drugbank_id, p_pubchem_cid, p_unii, p_cas_number, p_rxcui, p_ndc, p_inn, p_name)` | `bigint` | InChIKey → ChEMBL → DrugBank → PubChem → UNII → CAS → RxCUI (IN/PIN) → NDC → INN → name → fuzzy ≥0.85 |
| `mol_silver.resolve_drug_product(p_ndc, p_rxcui, p_bla, p_application_number, p_ema_product_number, p_cvx, p_ingredients_hash, p_brand, p_generic, p_dosage_form, p_strength_mg, p_route)` | `bigint` | NDC → RxCUI (SCD/SBD/GPCK/BPCK only) → BLA + product → NDA + product → EMA → CVX → ingredient hash → brand+form+strength → generic+form+strength → brand → fuzzy ≥0.85 |
| `mol_silver.resolve_target(p_uniprot_id, p_chembl_target_id, p_gene_symbol, p_entrez_id, p_ensembl_id, p_sequence_hash, p_pdb_id, p_name)` | `bigint` | UniProt → ChEMBL target → HUGO gene → Entrez → Ensembl → sequence hash → PDB → normalized name → fuzzy ≥0.85 |
| `ind_silver.resolve_condition(p_icd11, p_icd10, p_mesh, p_meddra_pt, p_name)` | `bigint` | ICD-11 → ICD-10 → MeSH → MedDRA PT → ICD-10 chapter → normalized name → fuzzy ≥0.85 |
| `mol_silver.resolve_company(p_cik, p_ticker, p_name, p_country)` | `bigint` | CIK → ticker → normalized name (after stripping `Inc.`/`Corp.`/`Ltd.`/`AG`/`SA`) → fuzzy ≥0.85 |
| `hcs_silver.resolve_provider(p_npi, p_pecos_id, p_first_name, p_last_name, p_state, p_taxonomy)` | `bigint` | NPI → PECOS ID → normalized (first+last+state+taxonomy) → fuzzy ≥0.85 |
| `hcs_silver.resolve_facility(p_ccn, p_npi_type2, p_ncdr_id, p_facility_name, p_city, p_state, p_zip)` | `bigint` | CCN → NPI type-2 → NCDR ID → normalized (name+city+state+ZIP) → fuzzy ≥0.85 |
| `hcp_silver.resolve_researcher(p_orcid, p_scopus_author_id, p_pubmed_signature, p_researchgate_id, p_google_scholar_id, p_full_name, p_institution, p_country)` | `bigint` | ORCID → Scopus author ID → normalized PubMed first/last author signature (`lower(lastname) \|\| '_' \|\| lower(firstinitial)`) → ResearchGate ID → Google Scholar ID → normalized `(full_name + institution + country)` → fuzzy on `full_name + institution` ≥0.85 |
| `ip_silver.resolve_patent(p_jurisdiction, p_patent_number, p_application_number, p_publication_number, p_pct_application, p_title, p_first_assignee, p_filing_year)` | `bigint` | (jurisdiction, patent) → (jurisdiction, application) → (jurisdiction, publication) → PCT → normalized title+assignee+year → fuzzy ≥0.85 |
| `ip_silver.resolve_trademark(p_jurisdiction, p_registration_number, p_serial_number, p_wipo_madrid_number, p_mark_text, p_nice_classes, p_owner)` | `bigint` | (jurisdiction, registration) → (jurisdiction, serial) → WIPO Madrid → normalized (mark_text + sorted(nice_classes) + jurisdiction) → fuzzy ≥0.85 |
| `ip_silver.resolve_design(p_jurisdiction, p_design_number, p_wipo_hague_number, p_locarno_classes, p_holder, p_filing_year)` | `bigint` | (jurisdiction, design) → WIPO Hague → normalized (sorted(locarno) + holder + year) → fuzzy ≥0.85 |

All functions are `STABLE PARALLEL SAFE`. All return NULL when no match is found at any tier.

## State transitions

| Entity | States | Transitions |
|---|---|---|
| `meta.refresh_state.status` | `in_progress`, `completed`, `failed` | `in_progress` → `completed` (procedure finishes); `in_progress` → `failed` (procedure errors); `completed` → `in_progress` (next refresh kicks off) |
| `meta.job_locks` row | exists / doesn't exist | INSERT on acquire; DELETE on release; auto-skipped via `expires_at < NOW()` if stale |
