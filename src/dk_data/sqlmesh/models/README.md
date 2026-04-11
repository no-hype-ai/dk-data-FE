# SQLMesh Models — Conventions and Patterns

This README documents column-retention patterns, JSONB carry-forward rules, and
column-name disambiguation conventions for all silver models in this project.

---

## FR-001 — Column Retention Contract

Every non-system column from a bronze upstream must appear in the downstream silver
model. The contract is enforced by `tests/test_silver_column_retention.py`.

### System/Exempt Columns

The following column names are intentionally excluded from silver models:

| Column              | Reason                                           |
|---------------------|--------------------------------------------------|
| `id`                | Bronze surrogate key, replaced by silver key     |
| `ingested_at`       | Bronze processing timestamp                      |
| `_loaded_at`        | Raw-layer load timestamp                         |
| `processed_to_silver` | Bronze staging flag                            |
| `processed_to_bronze` | Raw staging flag                               |
| `source`            | Overridden in silver with canonical source name  |
| `source_updated_at` | Managed by silver model                          |
| `raw_id`            | Raw-layer row identifier                         |
| `raw_json`          | Raw HTTP response envelope                       |
| `request_id`        | HTTP request tracking                            |
| `request_timestamp` | HTTP request time                                |
| `row_hash`          | Deduplication hash                               |
| `batch_id`          | Batch load identifier                            |
| `raw_source_id`     | Internal bronze request tracking                 |
| `response_body`     | Raw HTTP response payload                        |
| `response_status`   | HTTP status code                                 |
| `_sqlmesh_start`    | SQLMesh incremental watermark                    |
| `_sqlmesh_end`      | SQLMesh incremental watermark                    |
| `_api_hidden`       | Internal API visibility flag                     |
| `created_at`        | Row creation timestamp (managed by silver)       |
| `updated_at`        | Row update timestamp (managed by silver)         |
| `_bronze_loaded_at` | HCS domain bronze load timestamp                 |

---

## FR-003 — JSONB Carry-Forward

JSONB columns from bronze **must** be carried as JSONB in silver — never cast to TEXT.
This preserves downstream query capabilities (JSON path operators, aggregation, indexing).

### JSONB Columns by Source

| Bronze Source         | JSONB Columns                                                |
|-----------------------|--------------------------------------------------------------|
| `mol_bronze.drugbank` | `targets`, `enzymes`, `carriers`, `transporters`,           |
|                       | `drug_interactions`, `pathways`, `products`, `patents`,     |
|                       | `external_links`, `external_identifiers`,                   |
|                       | `calculated_properties`, `experimental_properties`          |
| `mol_bronze.chembl_molecules` | `synonyms`, `cross_references`                     |
| `mol_bronze.uspto_patents`    | `cpc_codes`, `inventors`                           |
| `mol_bronze.epo_patents`      | `ipc_codes`, `cpc_codes`, `inventors`              |
| `mol_bronze.euipo_trademarks` | `nice_classes`                                     |
| `mol_bronze.euipo_designs`    | `locarno_classes`                                  |
| `mol_bronze.uspto_trademarks` | `nice_classes`, `us_classes`                       |
| `mol_bronze.uniprot`  | `go_terms`, `pdb_structures`, `keywords`, `features`,       |
|                       | `comments`, `cross_references`, `genes`                     |
| `mol_bronze.pubchem`  | `pharmacological_actions`, `synonyms`, `mesh_headings`,     |
|                       | `assay_ids`, `drugbank_ids`, `chembl_ids`, `taxonomy`       |

---

## FR-002 — Column-Name Disambiguation

When a silver model draws from **two or more bronze sources** that have columns
with the same logical name (e.g., both `mol_bronze.chembl_molecules` and
`mol_bronze.drugbank` have a `canonical_smiles`), prefix the output column with
the source name:

```sql
-- Example: mol_silver.molecules with competing canonical_smiles
c.canonical_smiles     AS chembl_canonical_smiles,
d.canonical_smiles     AS drugbank_canonical_smiles,
```

For columns that only one source provides, use the unqualified name:

```sql
c.chembl_id,          -- only chembl_molecules has this
d.drugbank_id,        -- only drugbank has this
```

---

## Selective Models

Some silver models intentionally extract a **semantic subset** of bronze columns
because they serve a specific analytical purpose rather than being full passthroughs.
These models are registered in `SELECTIVE_MODELS` in the test file and are exempt
from strict column-retention enforcement.

Examples:
- **`molecules.sql`** — Entity resolution model; creates a canonical molecule master
  from ChEMBL, DrugBank, and PubChem. Only canonical identity fields are retained.
- **`identifier_mappings.sql`** — Cross-reference table; only identifier fields
  (ChEMBL ID, DrugBank ID, PubChem CID, etc.) are extracted.
- **`molecule_aliases.sql`** — Alias extraction; only name/alias fields are retained.
- **`bioactivity.sql`** — Extracts specific assay columns from ChEMBL activities.
- **`pathways.sql`** — Extracts pathway data from KEGG/Reactome.

When adding a new selective model, document the reason in `SELECTIVE_MODELS` within
`tests/test_silver_column_retention.py`.

---

## Domain Directory Structure

```
models/
├── molecules/        mol_* schemas — drug/compound data
│   ├── bronze/       mol_bronze — typed extraction from mol_raw
│   ├── silver/       mol_silver — entity-resolved, normalized
│   └── gold/         mol_gold — aggregated analytics
├── hcs/              hcs_* schemas — healthcare system/CMS data
│   ├── bronze/       hcs_bronze
│   ├── silver/       hcs_silver
│   └── gold/         hcs_gold
├── ind/              ind_* schemas — indication/disease/epidemiology
│   ├── bronze/       ind_bronze
│   ├── silver/       ind_silver
│   └── gold/         ind_gold
├── ip/               ip_* schemas — intellectual property (patents, trademarks, designs)
│   ├── bronze/       ip_bronze
│   ├── silver/       ip_silver
│   └── gold/         ip_gold
├── hcp/              hcp_* schemas — healthcare professionals/KOLs
└── mart/             mart schema — pre-computed data marts
```

---

## IP Domain Migration

The `ip_*` domain was split from `mol_*` in feature `001-silver-medallion-rebuild`.
Patent and trademark models were moved from `mol_bronze`/`mol_silver` to
`ip_bronze`/`ip_silver` as these are domain-independent intellectual property assets.

**Moved models:**
- `ip_bronze.{uspto_patents, uspto_ci, uspto_trademarks, epo_patents, euipo_trademarks, euipo_designs, trademark_status_history}`
- `ip_silver.{patents, trademarks, patent_exclusivities, trademark_status_changes, designs}`

See `.dk/specs/001-silver-medallion-rebuild/` for the full migration rationale.
