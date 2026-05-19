# Entity Linking Strategy

**Feature**: 019-cms-puf-platform-reconciliation
**Status**: Implemented

---

## Overview

The goal is: given any molecule (drug), retrieve all data from all external sources.
Given any provider (NPI), retrieve all CMS utilization data.
Given a molecule AND a provider, find prescribing patterns, spend, and adverse events.

Entity linking uses four strategies depending on the source and domain.

---

## Molecule Domain

### Master Entity Table: `mol_silver.molecules`

- **Primary key**: `molecule_id = md5(chembl_id::text)::uuid` — deterministic, stable across full rebuilds
- **Unique key**: `chembl_id` — ChEMBL covers ~2M compounds including biologics
- **Biologic support**: `inchi_key` may be NULL for biologics; `chembl_id` is always required
- **Sources**: ChEMBL (master) + DrugBank enrichment + PubChem enrichment
- **Kind**: `FULL` — rebuilds daily; deterministic UUID means FK relationships don't break

```
ChEMBL   ──────────────────► mol_silver.molecules (molecule_id, chembl_id)
DrugBank ─► inchi_key join ──► (+ drugbank_id, mechanism_of_action, unii, cas_number)
          └► name fallback ──► (biologics: NULL inchi_key, match on canonical_name)
PubChem  ─► inchi_key join ──► (+ pubchem_cid)
```

---

### Strategy 1: Structural (small molecules)

**Join key**: `inchi_key` (27-char InChI Key, unique structural fingerprint)

Used for: deduplication across ChEMBL, DrugBank, PubChem.

```sql
-- Example: find the same molecule across sources
SELECT * FROM mol_silver.molecules m
WHERE m.inchi_key = 'XUJNEKJLAYQKCS-UHFFFAOYSA-N'  -- aspirin
```

**Limitation**: biologics (antibodies, proteins, oligonucleotides) have no InChI Key.
**Fallback**: name-based join (`LOWER(pref_name) = LOWER(drugbank.name)`).

---

### Strategy 2: 3-Tier Priority (clinical trials → molecules)

**Used in**: `mol_silver.clinical_trials`
**Join key**: drug name text matching against `mol_silver.molecules.canonical_name`

| Tier | Match | Confidence |
|------|-------|-----------|
| 0 | Exact: `LOWER(queried_drug_name) = canonical_name` | Highest |
| 1 | Substring: `queried_drug_name LIKE '%' \|\| canonical_name \|\| '%'` | Medium |
| 2 | Fuzzy: title or intervention text contains canonical_name | Lowest |

**`queried_drug_name`** is preserved so analysts can audit the match.

```sql
-- Find all trials for a molecule
SELECT ct.nct_id, ct.title, ct.phase, ct.overall_status
FROM mol_silver.clinical_trials ct
WHERE ct.molecule_id = (
    SELECT molecule_id FROM mol_silver.molecules WHERE chembl_id = 'CHEMBL25'
)
```

---

### Strategy 3: Alias Bridge (adverse events / FAERS → molecules)

**Used in**: `mol_silver.adverse_events`, `mol_silver.hcpcs_molecule_bridge`
**Bridge table**: `mol_silver.molecule_aliases`
**Join key**: `alias_name_normalized` (all punctuation stripped, lowercase)

FAERS drug names are verbatim strings — often brand names, abbreviations, or misspellings.
The alias table aggregates ALL known names from ALL sources:

| Alias Type | Source |
|---|---|
| `canonical` | ChEMBL pref_name |
| `synonym` | ChEMBL synonyms, DrugBank synonyms, PubChem synonyms |
| `brand` | DrugBank international_brands, FDA drug labels |
| `product` | DrugBank product names |
| `generic` | FDA drug labels generic_name |
| `trade` | Orange Book trade names |
| `trial_intervention` | ClinicalTrials.gov intervention names |

```sql
-- FAERS drug_name → alias_name_normalized → molecule_id
JOIN mol_silver.molecule_aliases ma
    ON LOWER(REGEXP_REPLACE(faers.drug_name, '[^a-zA-Z0-9]', '', 'g'))
     = ma.alias_name_normalized
```

---

### Strategy 4: Cross-Source Identifier Bridge

**Table**: `mol_silver.identifier_mappings`
**Grain**: `(molecule_id, identifier_type, identifier_value)`

| Identifier Type | Source | Confidence |
|---|---|---|
| `chembl_id` | ChEMBL | 1.00 |
| `drugbank_id` | DrugBank | 0.95 |
| `unii` | DrugBank → FDA | 0.95 |
| `rxcui` | FDA drug labels → RxNorm | 0.95 |
| `pubchem_cid` | PubChem | 0.90 |
| `cas_number` | DrugBank | 0.90 |
| `uniprot_id` | ChEMBL targets | 0.90 |
| `ndc` | FDA drug labels | 0.90 |

```sql
-- Find molecule from an NDC
SELECT m.*
FROM mol_silver.identifier_mappings im
JOIN mol_silver.molecules m ON m.molecule_id = im.molecule_id
WHERE im.identifier_type = 'ndc'
  AND im.identifier_value = '0069-3060-30'  -- Lipitor 10mg
```

---

## CMS → Molecule Linking (New in 019)

CMS data uses drug names (Part D), NDC codes (pharmacy claims), and HCPCS codes (Part B).
None of these map directly to `chembl_id` — two bridge tables close this gap.

### NDC Bridge: `mol_silver.ndc_molecule_bridge`

**NDC** (National Drug Code) → `molecule_id`

Sources: FDA drug labels (ndc_codes JSONB array + molecule_id already linked).
An NDC maps to exactly one drug product; one molecule may have hundreds of NDCs
(different manufacturers, dosages, package sizes).

```sql
-- All CMS Part D spend for molecule X
SELECT du.drug_or_hcpcs_code, du._source_year, du.total_cost
FROM hcs_silver.drug_utilization du
WHERE du.molecule_id = (
    SELECT molecule_id FROM mol_silver.molecules WHERE chembl_id = 'CHEMBL1201207'
)
  AND du.code_type = 'part_d_drug'
```

### HCPCS Bridge: `mol_silver.hcpcs_molecule_bridge`

**HCPCS code** (J-codes, Q-codes, etc.) → `molecule_id`

Drug J-codes are infusion/injection billing codes used in CMS Part B.
Confidence is 0.75 (text match on description, not structural ID).
Prefer NDC bridge where available.

```sql
-- Part B infusion spend for a drug
SELECT du.drug_or_hcpcs_code, hb.hcpcs_description, du.total_cost
FROM hcs_silver.drug_utilization du
JOIN mol_silver.hcpcs_molecule_bridge hb ON du.drug_or_hcpcs_code = hb.hcpcs_code
WHERE hb.molecule_id = (
    SELECT molecule_id FROM mol_silver.molecules WHERE chembl_id = 'CHEMBL3707160'
)
  AND du.code_type IN ('dme_hcpcs', 'imaging_hcpcs')
```

---

## HCS / Provider Domain

### Master Entity Table: `hcs_silver.provider_profile`

- **Primary key**: `npi` (10-digit NPI, National Provider Identifier)
- **Version key**: `_source_year` — annual CMS snapshots
- **Sources merged**: NPPES (authoritative) > Physician PUF > DME > Mental Health > Telehealth > Hospice
- **Kind**: `INCREMENTAL_BY_UNIQUE_KEY (npi, _source_year)`

```
CMS NPPES          ──► hcs_silver.provider_profile (npi — authoritative identity)
CMS Physician PUF  ──► (+ utilization, procedure counts, HCPCS codes)
CMS DME PUF        ──► (+ DME utilization)
CMS Mental Health  ──► (+ mental health services)
CMS Telehealth     ──► (+ telehealth services)
CMS Hospice        ──► (+ hospice services)
```

**Provider → Drug linkage**:
- `hcs_silver.drug_utilization` — drug-level spend (no NPI dimension)
- `hcs_silver.part_d_prescribing` — NPI × generic drug × year, with `molecule_id` (feature 020)
- `hcs_silver.open_payments_drug_linkage` — industry payments per NPI × drug, with `molecule_id` (feature 020)

---

## Cross-Domain Query Patterns

### "For molecule X, show all data"

```sql
-- Step 1: get molecule_id
SELECT molecule_id FROM mol_silver.molecules WHERE chembl_id = 'CHEMBL25';

-- Step 2: clinical trials
SELECT nct_id, phase, overall_status FROM mol_silver.clinical_trials
WHERE molecule_id = $mol_id;

-- Step 3: adverse events
SELECT meddra_pt, report_count, death_count FROM mol_silver.adverse_events
WHERE molecule_id = $mol_id ORDER BY report_count DESC;

-- Step 4: drug spend (Part D)
SELECT _source_year, total_cost, total_claims FROM hcs_silver.drug_utilization
WHERE molecule_id = $mol_id AND code_type = 'part_d_drug';

-- Step 5: all external identifiers
SELECT identifier_type, identifier_value, confidence
FROM mol_silver.identifier_mappings WHERE molecule_id = $mol_id;
```

### "For FAERS drug name X, find the molecule"

```sql
SELECT DISTINCT m.chembl_id, m.canonical_name, m.molecule_type, m.max_phase
FROM mol_silver.molecule_aliases ma
JOIN mol_silver.molecules m ON m.molecule_id = ma.molecule_id
WHERE ma.alias_name_normalized = LOWER(REGEXP_REPLACE('KEYTRUDA', '[^a-zA-Z0-9]', '', 'g'));
```

### "Which providers prescribe molecule X (Part D)"

```sql
SELECT pp.npi, pp.canonical_name, pp.prscrbr_state_abrvtn,
       pd.tot_clms, pd.tot_drug_cst, pd.link_confidence
FROM hcs_silver.part_d_prescribing pd
LEFT JOIN hcs_silver.provider_profile pp
    ON pd.prscrbr_npi = pp.npi AND pd._source_year = pp._source_year
WHERE pd.molecule_id = $mol_id
  AND pd.molecule_resolved = TRUE
ORDER BY pd.tot_drug_cst DESC;
```

### "Which manufacturers paid physicians for drug X (Open Payments)"

```sql
SELECT op.physician_first_name, op.physician_last_name, op.physician_specialty,
       op.applicable_manufacturer_or_gpo_name,
       SUM(op.total_amount_of_payment_usdollars) AS total_payments,
       op._source_year
FROM hcs_silver.open_payments_drug_linkage op
WHERE op.molecule_id = $mol_id
  AND op.molecule_resolved = TRUE
GROUP BY 1, 2, 3, 4, op._source_year
ORDER BY total_payments DESC;
```

---

## Resolved Gaps (feature 020)

| Gap | Status | Resolution |
|---|---|---|
| NPI-level Part D prescribing not in silver | ✅ Resolved | `hcs_silver.part_d_prescribing` — NPI × drug × year with molecule_id (confidence 0.85) |
| `therapeutic_areas` in molecules not populated | ✅ Resolved | Aggregated from `mol_silver.clinical_trials.conditions` JSONB into `mol_silver.molecules.therapeutic_areas` |
| HCPCS bridge confidence is 0.75 (first-word only) | ✅ Improved | Tiered matching: first-token = 0.85, substring = 0.75. Raises recall without reducing precision |
| CMS Open Payments drug names not linked | ✅ Resolved | `hcs_silver.open_payments_drug_linkage` — NDC path (0.95) + alias path (0.75) per drug slot |

## Remaining Limitations

| Item | Impact | Next action |
|---|---|---|
| HCPCS bridge: no FDA structural crosswalk | 0.85 ceiling on HCPCS confidence | Add if FDA HCPCS→NDC crosswalk becomes available |
| Open Payments: pre-2016 files have different schema | Drug slot column names differ before 2016 | Add year-conditional COLUMN_MAPPING in loader if loading pre-2016 data |
| Part D Prescriber: suppressed rows (< 11 benes) | Some prescribers × drugs excluded by CMS | Inherent CMS privacy suppression — no fix available |
