# Source × Entity × Identifier Reference

This is the canonical reference for what each dk-data source contains and what identifiers it emits. Sourced from `silver-linkage-reference.md`. Used by hub bootstrap procedures and silver enrichment models.

Entity codes: **M** = molecule, **B** = biologic, **C** = combination drug, **T** = target, **I** = indication, **AE** = adverse event, **Path** = pathway, **Reg** = regulatory, **Co** = company, **Pat** = patent.

## Molecule sources

| Source | Primary key | Entities | Identifiers emitted | Notes |
|---|---|---|---|---|
| **chembl_molecules** | molecule_chembl_id | M, B | chembl_id, **inchi_key**, canonical_smiles, inchi, molecular_formula, pref_name, synonyms (incl. TRADE_NAME, INN), cross_references (DrugBank/PubChem/UNII), molecule_type | Drug entity spine. `molecule_type` distinguishes small molecule from Protein/Antibody/Cell/Oligo |
| **chembl_activities** | activity_id | M↔T binding | chembl_id, target_chembl_id | 25M+ rows. Already in bronze. |
| **drugbank** | drugbank_id | M, B, T, Path, AE, I | drugbank_id, **cas_number**, **unii**, name, smiles, inchi, **inchi_key**, synonyms[], international_brands[], atc_codes[] | XML, credential-gated. Has `<biotech>` branch for biologics. |
| **pubchem** | cid | M | cid, **inchi_key**, canonical_smiles, isomeric_smiles, iupac_name, mesh_headings[], cas (xref), chembl_ids (xref), drugbank_ids (xref), unii (xref), rxcui (xref) | **Small molecules only — no biologics** |
| **who_inn** | inn_name | M, B | **inn_name**, cas_number, inchi_key, smiles, molecular_formula, **inn_stem** (-mab, -tinib, etc.), research_codes[] | INN names with biologic stems (`-mab`, `-cept`, `-tide`) |
| **rxnorm** | rxcui | M, B, **C** | rxcui, tty (IN, PIN, **SCD**, **SBD**, BN, GPCK, BPCK), name, brand_names[], ndc_codes[], **ingredient_set[]** for combos | SCD/SBD concepts have explicit ingredient sets |
| **fda_ndc** (openFDA) | product_ndc | M, B, **C** | product_ndc, package_ndcs[], generic_name, brand_name, **active_ingredients[]** for combos, openfda.unii[], openfda.rxcui[], openfda.atc[] | openFDA harmonization gives us UNII + RxCUI |
| **fda_drugs** (Drugs@FDA) | application_number, product_number | M, B, Reg, Co | appl_no, product_no, brand_name, generic_name (active_ingredient), sponsor, drug_type | |
| **openfda_labels** (SPL) | set_id | M, B, I, AE, Reg | set_id, spl_id, brand_name, generic_name, **unii[]**, **rxcui[]**, **ndc[]**, **substance_name[]** for combos | openFDA harmonization arrays |
| **dailymed** | set_id | M, B, **C**, I, AE | set_id, title, generic, brand, NDC, **active_ingredients[]** | Full label text |
| **orange_book** | (appl_no, product_no, patent_no) | M, **C**, Pat, Reg | application_number, product_number, **ingredient** (semicolon-delimited for combos), trade_name, te_code, patent_number | Small molecules. Combo via semicolon split. |
| **purple_book** | (bla_number, product_number) | **B** | bla_number, product_number, brand_name, generic_name, **reference_product_name** for biosimilars, is_biosimilar, is_interchangeable, dosage_form, route, strength | The only source with biosimilar↔reference linkage. Borderline v1 — see deferred items Gap 9. |
| **fda_rems** | rems_id | M, B, Reg | rems_id, brand_name, generic_name | |
| **kegg_drug** | kegg_id | M, B, Path, T | kegg_id (D-number), drugbank_id, chembl_id, cas_number, names[] | Cross-refs |
| **ttd** | ttd_drug_id | M↔T↔I | ttd_drug_id, drug_name | |
| **pharmgkb** | pharmgkb_accession | M↔Gene↔I | pharmgkb_accession, cross_refs (drugbank, chembl, rxnorm, atc) | |
| **bindingdb** | bdbm_id | M↔T affinities | bdbm_id, **inchi_key**, smiles, chembl_id, drugbank_id, uniprot_id | 4M+ rows |
| **tdc_admet** | (compound_id, dataset_name) | M ADMET | inchi_key, smiles, compound_id | |
| **sider** | (stitch_flat_id, side_effect) | M↔AE | stitch_flat_id, drug_name, meddra_pt, meddra_llt | |
| **ema_mol / ema_regulatory** | ema_product_number | M, B, Reg | ema_product_number, active_substance (INN), brand_name, atc_code | |
| **cdc_vaccines** | cvx_code | **B** | cvx_code, vaccine_name | Vaccine-specific CVX codes |
| **imgt** | imgt_id | **B** (antibodies) | imgt_id, antibody sequence, clone name | Deferred — see Gap 10 |

## Target sources

| Source | Primary key | Identifiers |
|---|---|---|
| **uniprot** | uniprot_id | uniprot_id, gene_name (HUGO), entrez_gene_id (xref), ensembl_id (xref), taxonomy_id, sequence, GO terms, PDB refs |
| **chembl_targets** (in chembl bronze) | chembl_target_id | chembl_target_id, uniprot_id, target_name, target_type, target_organism |
| **pdb** | pdb_id | pdb_id, uniprot_id, structure_method, resolution |

## Indication / disease sources

| Source | Primary key | Identifiers | Status |
|---|---|---|---|
| **who_icd** | (icd_version, code) | icd10_code, icd11_code, definition, parent_code | Ingested |
| MeSH | mesh_id | (via PubMed/PubChem cross-refs) | Ingested |
| MedDRA | meddra_pt | meddra_pt, meddra_llt; HLT/HLGT/SOC missing | PT level only — see Gap 7 |
| SNOMED CT | sctid | — | Not ingested (license required) — see Gap 6 |
| MONDO | mondo_id | — | Not ingested |
| OMIM | omim_id | — | Not ingested |
| drugbank.indication | structured `<conditions>` | DrugBank `<conditions>` linked elements give us most indication→ICD/MeSH mappings without prose parsing | Used in v1 |
| clinicaltrials.conditions | structured via `derivedSection.conditionMeshList` | ClinicalTrials.gov MeSH-indexes every trial; we read `derivedSection.conditionMeshList[]` directly | Used in v1 (FR-032) |
| openfda_labels.indications_and_usage | (free text) | Indication enrichment from prose deferred; v1 uses `openfda.unii`/`rxcui` for drug ID and DrugBank/ChEMBL/drugs@FDA for drug→indication | Deferred |
| cms_coverage NCDs | (free text) | Deferred — limited consumer use case | Deferred |
| faers.drugindication | (free text) | Deferred — `patient.reaction[].reactionmeddrapt` already provides structured AE coding | Deferred |

## Trial / publication / patent sources

| Source | Primary key | Identifiers |
|---|---|---|
| **clinicaltrials** | nct_id | nct_id, org_study_id, secondary_ids[], eudract_number, derivedSection.interventionMeshList[], derivedSection.conditionMeshList[] |
| **europepmc** | (source, ext_id) | pmid, doi, pmcid, europepmc_id, mesh_headings |
| **pubmed** | pmid | pmid, doi, pmcid, mesh_headings, abstract, MeshHeadingList[], ChemicalList[] |
| **cochrane** | doi | doi |
| **openalex_ci** | openalex_id | openalex_id, doi, pmid, pmcid, institution ROR |
| **journal_rss** | guid | doi, guid |
| **medical_news** | url | url, title (free text — WHO INN regex extraction per FR-035) |
| **uspto_patents** | patent_number | patent_number, application_number, assignees[], cpc_codes[]. FDA-drug linkage via Orange Book join (FR-034). |
| **uspto_ci** | (patent_number, transaction) | patent_number |
| **epo_patents** | publication_id | publication_id (EP), applicants[] |
| **uspto_trademarks / euipo_trademarks** | serial_number / registration_number | mark_text, owner_name, nice_classes[] |
| **euipo_designs** | design_number | design_number, holder, locarno_class[] |
| **nice_hta / hta_decisions** | decision_id | decision_id; drug + indication are free text — deferred |

## Provider / facility sources

| Source | Primary key | Identifiers | Notes |
|---|---|---|---|
| **cms_nppes / npi_registry** | npi | npi, entity_type (1=individual, 2=org), taxonomy_codes[], addresses[], names | Canonical source for NPI |
| **cms_nucc** | taxonomy_code | taxonomy_code, classification, specialization | |
| **cms_pecos** | (npi, pecos_id) | npi, pecos_id, enrollment_date | |
| **cms_hospital_general_info** | facility_id (CCN) | CCN, hospital_ownership, hospital_type, rating | Canonical facility source |
| **cms_hospital_affiliation** | (npi, facility_id) | npi, ccn | Provider↔facility bridge |
| **cms_hospital_quality / cms_care_compare / cms_pos / cms_chow** | facility_id / ccn | CCN | |
| **cms_inpatient_puf** | (provider_id, drg_cd, _source_year) | CCN, drg_cd | |
| **cms_outpatient_puf** | (provider_id, apc, _source_year) | CCN, apc | |
| **cms_physician_puf / cms_physician_puf_services** | (npi, hcpcs_cd, _source_year) | NPI, HCPCS | |
| **cms_part_d_prescriber** | (prscrbr_npi, gnrc_name, _source_year) | NPI, brand_name + generic_name (no NDC at row level) | Tier 2 — RxNorm BN/IN lookup (FR-068) |
| **cms_open_payments** | (record_id, _source_year) | NPI, product_name (free text) | Tier 2 — direct alias lookup against `mol_silver.molecule_names` (FR-068) |
| **acc_tvc** | (facility_name, state, certification_type) | facility_name, state, **NO CCN** | Tier 2 — fuzzy → CCN (FR-068) |
| **cms_magnet** | (facility_name, city, state) | facility_name, city, state, **NO CCN** | Tier 2 — trigram fuzzy → CCN (FR-068) |
| **hrsa** | hpsa_id | hpsa_id, facility_name, address, **NO CCN/NPI** | Tier 2 — fuzzy/geocode → CCN+NPI (FR-068) |

## KOL / researcher sources (`hcp_silver.researchers`)

| Source | Primary key | Identifiers emitted | Notes |
|---|---|---|---|
| **pubmed** (existing bronze) | pmid | `MedlineCitation.Article.AuthorList.Author[]` — each author has `LastName`, `ForeName`, `Initials`, `Identifier[@Source='ORCID']`, `AffiliationInfo[].Affiliation` | The primary author / KOL source. ~30M PubMed records with ~50M unique authors after dedup. Used by FR-036e. |
| **europepmc** (existing bronze) | (source, ext_id) | Same author + affiliation structure as PubMed; extends coverage to non-US journals | Used by FR-036e. |
| **openalex_ci** (existing bronze) | openalex_id | `authorships[].author.id` (OpenAlex author ID), `authorships[].author.scopus_id`, `authorships[].author.orcid`, `authorships[].institutions[].ror`, `authorships[].institutions[].display_name` | Provides Scopus author ID + ROR institution ID — both critical for cross-referencing. Used by FR-036e tier 2. |
| **orcid** (NOT YET INGESTED — see deferred Gap 11) | orcid_id | orcid_id, full_name, employments[], educations[], works[] | The canonical international researcher identifier. Free + open API. Bootstrap can populate `hcp_silver.researchers.orcid_id` from OpenAlex (which already has ORCID xrefs) without ingesting ORCID directly. |
| **scopus** / Elsevier (NOT INGESTED — paid) | scopus_author_id | scopus_author_id, h-index, co-author network | Best commercial KOL data. Paid license required. Deferred. |
| **researchgate** / **google_scholar** (NOT INGESTED — scraping required) | researchgate_id / scholar_id | profile_id, h-index, recent_pubs | Both lack public bulk APIs. Web scraping is fragile + ToS-restricted. Deferred to a follow-up that licenses Cortellis Speaker Data or H1 Insights instead. |
| **clinicaltrials.gov** investigators | (nct_id, investigator_position) | `protocolSection.contactsLocationsModule.overallOfficials[].name`, `affiliation` | Trial-derived KOL identification — clinical-investigator side. Useful complement to publication-derived KOLs. Already in `mol_bronze.clinicaltrials`. |

**Researcher resolution priority** (`hcp_silver.resolve_researcher`):
1. ORCID iD (Pattern B — international standard)
2. Scopus author ID (Pattern B — Elsevier's identifier)
3. PubMed first/last author signature `(lower(LastName) || '_' || lower(left(ForeName,1)))` (Pattern B-derived)
4. ResearchGate ID (Pattern B — when scraped or licensed)
5. Google Scholar ID (Pattern B — when scraped)
6. Normalized `(full_name + primary_affiliation_institution + country)` (Pattern C composite)
7. Trigram fuzzy on `full_name + ' ' + institution` ≥ 0.85 (Pattern D)

**Cross-references**:
- `hcp_silver.researcher_publications` ↔ PubMed PMID — joins to `mol_silver.pubmed_articles.molecule_id` and `condition_id` for "what does this researcher publish about?"
- `hcp_silver.researcher_affiliations` ↔ `mol_silver.companies.company_id` — populated when `affiliation_type = 'industry'` and the institution name resolves to a known pharma/biotech company. Answers "which researchers have industry affiliations and with which companies?"
- `hcp_silver.researcher_provider_crosswalk` ↔ `hcs_silver.providers.provider_id` — populated by fuzzy-matching researcher names + institutions against NPPES practice locations. Answers "is this published author also a practicing prescriber?"

**The provider hub vs the researcher hub** — they are deliberately separate even though the same physical person may appear in both. Providers are NPI-keyed regulatory entities (Medicare-billable prescribers); researchers are publication-derived KOLs identified by ORCID + Scopus + PubMed signature. The crosswalk table is the bridge. This split matches how commercial pharma intelligence platforms (Veeva OpenData, IQVIA OneKey, Definitive Healthcare, H1 Insights) organize their data: prescriber data feeds market intelligence and Open Payments analysis; KOL data feeds medical affairs, advisory board recruitment, and speaker bureau management.

## Company sources

| Source | Primary key | Identifiers | Status |
|---|---|---|---|
| **sec_edgar** | (cik, accession_number) | cik, ticker, company_name | US public companies + foreign private issuers (20-F, 6-K, 40-F). Financial fields are NULL in v1; XBRL bulk-download deferred. |
| fda_drugs.applicant_full_name | (free text) | — | Fuzzy match in v1 |
| ema_mol.marketing_authorisation_holder | (free text) | — | Fuzzy match in v1 |
| uspto_patents.assignees | (free text) | — | Fuzzy match in v1 |
| DUNS / LEI / ROR / GRID | — | — | Not ingested — see Gap 5 |

---

## Biologics support matrix

| Source | Has biologics? | Has biologic identifier? | Canonical biologic key in v1 |
|---|---|---|---|
| ChEMBL | ✅ | molecule_chembl_id but no InChIKey | `'biologic:' \|\| lower(pref_name)` (current fallback) |
| DrugBank | ✅ | drugbank_id, no InChIKey for biotech | `'biologic:' \|\| lower(name)` |
| PubChem | ❌ | — | (small molecules only) |
| **Purple Book** | ✅ canonical source | ✅ BLA + product | Borderline v1 — Gap 9 |
| WHO INN | ✅ | INN name with biologic stems | INN name |
| IMGT | ✅ antibodies | ✅ IMGT ID + sequence | Deferred — Gap 10 |
| UniProt | ✅ proteins | ✅ uniprot_id + sequence | UniProt ID (only for human/known) |
| openFDA labels | ✅ | UNII + RxCUI + NDC | UNII |
| FDA NDC | ✅ | UNII + NDC | UNII or NDC |
| CDC Vaccines | ✅ vaccines | ✅ CVX code | CVX code |
| RxNorm | ✅ | RxCUI | RxCUI (SCD/SBD only — see FR-012) |
| Orange Book | ❌ | (small molecules only) | — |
| Drugs@FDA | ✅ | application_number | application_number |
| FAERS | ✅ (structured) | `openfda.unii[]`, `openfda.rxcui[]`, `openfda.product_ndc[]`, `openfda.substance_name[]`; reactions via `reactionmeddrapt` | UNII / RxCUI / NDC / substance_name |

**Coverage gaps**:
1. Purple Book biosimilar↔reference linkage — borderline v1 (Gap 9)
2. No sequence-hash tier in v1 for biologics not in UniProt
3. IMGT antibody clone names — deferred (Gap 10)

## Combination drug coverage matrix

| Source | Combo representation | Quality |
|---|---|---|
| **RxNorm** | SCD/SBD concepts have explicit ingredient sets | ✅ Best — used by `mol_silver.drug_products` (FR-012) |
| **Orange Book** | semicolon-delimited ingredient list | ⚠️ Needs parsing |
| **FDA NDC** | active_ingredients[] array of {name, strength} | ✅ Good — used in bootstrap |
| **openFDA labels** | substance_name[] array | ✅ Good — used in bootstrap |
| **DrugBank** | mixtures field (XML) | ⚠️ Needs extraction |
| **FAERS** | primary suspect + concomitant in all_drugs JSONB | ⚠️ Free text — handled via `openfda.*` arrays per drug entry |
| **ChEMBL** | Primarily single molecule; combos inconsistent | ❌ Poor — not used for combo enumeration |
| **Drugs@FDA** | active_ingredient sometimes combo | ⚠️ Inconsistent |

**Implementation**: `mol_silver.drug_products` represents the combination (SCD/SBD level — FR-012); `mol_silver.drug_product_ingredients` is the many-to-many link to ingredient molecules with `strength_value`, `strength_unit`, `is_active`, `ingredient_order` (FR-011).

---

## Reference query patterns (after hubs are built)

### "Show me everything we know about Sildenafil"

```sql
WITH sildenafil AS (
    SELECT molecule_id FROM mol_silver.molecules WHERE canonical_name ILIKE 'sildenafil'
    UNION
    SELECT molecule_id FROM mol_silver.molecule_identifiers
    WHERE source = 'chembl' AND identifier = 'CHEMBL192'
)
SELECT 'activities' AS source, count(*) AS records FROM mol_silver.bioactivity
WHERE molecule_id IN (SELECT molecule_id FROM sildenafil)
UNION ALL SELECT 'trials', count(*) FROM mol_silver.clinical_trials
WHERE molecule_id IN (SELECT molecule_id FROM sildenafil)
UNION ALL SELECT 'adverse events', count(*) FROM mol_silver.adverse_events
WHERE molecule_id IN (SELECT molecule_id FROM sildenafil)
UNION ALL SELECT 'labels', count(*) FROM mol_silver.openfda_labels
WHERE molecule_id IN (SELECT molecule_id FROM sildenafil);
```

No name matching. No fuzzy joins. No correlated subqueries. Just integer FK lookups.

### "Find all hospitals affiliated with Dr. John Smith (NPI 1234567890)"

```sql
WITH provider AS (
    SELECT provider_id FROM hcs_silver.provider_identifiers
    WHERE source = 'nppes' AND identifier = '1234567890'
)
SELECT f.facility_name, f.city, f.state, f.zip
FROM hcs_bronze.cms_hospital_affiliation a
JOIN hcs_silver.provider_identifiers pi ON pi.source = 'nppes' AND pi.identifier = a.npi
JOIN hcs_silver.facility_identifiers fi ON fi.source = 'ccn' AND fi.identifier = a.ccn
JOIN hcs_silver.facilities f ON f.facility_id = fi.facility_id
WHERE pi.provider_id IN (SELECT provider_id FROM provider);
```

### "Get adverse events for Combivent (the combination product)"

```sql
WITH combivent AS (
    SELECT product_id FROM mol_silver.drug_products WHERE brand_name ILIKE 'combivent'
),
combivent_ingredients AS (
    SELECT molecule_id FROM mol_silver.drug_product_ingredients
    WHERE product_id IN (SELECT product_id FROM combivent)
)
SELECT
    ae.event_id,
    ae.reaction_meddra_pt,
    CASE
        WHEN ae.product_id IN (SELECT product_id FROM combivent) THEN 'product-attributed'
        WHEN ae.molecule_id IN (SELECT molecule_id FROM combivent_ingredients) THEN 'ingredient-attributed'
    END AS attribution
FROM mol_silver.adverse_events ae
WHERE ae.product_id IN (SELECT product_id FROM combivent)
   OR ae.molecule_id IN (SELECT molecule_id FROM combivent_ingredients);
```

The product/ingredient distinction is preserved (FR-011). AE attribution is queryable. This is the test query for Gap 2 (combination drug AE attribution) — v1 leaves attribution at the `'product-attributed' / 'ingredient-attributed'` granularity; finer per-ingredient causal attribution is deferred.
