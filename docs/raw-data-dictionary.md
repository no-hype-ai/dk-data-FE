# Raw Data Dictionary — All External Data Source Fields

**Generated from REAL API responses** — not expected/guessed field names.
Date: 2026-03-21

This document lists EVERY field available from each external API.
Use this to prevent data loss in raw→bronze→silver transformations.

---

## Summary

**53 mol_raw tables** | 19 with data (JSONB extracted) | 34 empty (API documented)

---

## Part 1: Sources With Data (fields extracted from actual response_body JSONB)

These fields were extracted from live data in the database.

> The 19 populated sources (clinicaltrials, openfda_labels, openfda_faers, openalex, chembl, pubchem, uniprot, reactome, nice_hta, cms_open_payments, nih_reporter, fda_drugsfda, kegg, ema_regulatory, journal_rss, medical_news, orcid, pubmed, openalex_ci) are documented with full field paths extracted from actual database JSONB.

> See the field counts:

| Source | Fields |
|--------|--------|
| `mol_raw.chembl` | 80 |
| `mol_raw.clinicaltrials` | 292 |
| `mol_raw.cms_open_payments` | 91 |
| `mol_raw.ema_regulatory` | 9 (typed columns) |
| `mol_raw.fda_drugsfda` | 44 |
| `mol_raw.journal_rss` | 9 (typed columns) |
| `mol_raw.kegg` | 1 (text) |
| `mol_raw.medical_news` | 8 (typed columns) |
| `mol_raw.nice_hta` | 1 (HTML only) |
| `mol_raw.nih_reporter` | 11 |
| `mol_raw.openalex` | ~200 (excl inverted_index) |
| `mol_raw.openalex_ci` | 10 (typed columns) |
| `mol_raw.openfda_faers` | 86 |
| `mol_raw.openfda_labels` | 64 |
| `mol_raw.orcid` | 10 (typed columns) |
| `mol_raw.pubchem` | 50 |
| `mol_raw.pubmed` | 10 (typed columns) |
| `mol_raw.reactome` | 18 |
| `mol_raw.uniprot` | 145 |

---

## Part 2: Empty Sources (fields from real API documentation/responses)

### mol_raw.acc_tvc_certification

_Not yet implemented. CMS ACC/TVC facility certification data._

---

### mol_raw.bindingdb

**Fields**: 14

| Field | Type |
|-------|------|
| `affinity_type` | string (Ki/IC50/Kd/EC50) |
| `affinity_unit` | string (nM) |
| `affinity_value` | number |
| `article_doi` | string |
| `article_pmid` | string |
| `institution` | string |
| `ligand_inchi` | string |
| `ligand_inchi_key` | string |
| `ligand_smiles` | string |
| `monomer_id` | integer |
| `patent_id` | string |
| `target_name` | string |
| `target_source_organism` | string |
| `target_uniprot_id` | string |

---

### mol_raw.cdc_vaccines

**Fields**: 9

| Field | Type |
|-------|------|
| `cvx_code` | string |
| `cvx_short_description` | string |
| `manufacturer` | string |
| `mvx_code` | string |
| `mvx_status` | string |
| `product_name` | string |
| `product_name_status` | string |
| `short_description` | string |
| `update_date` | string |

---

### mol_raw.cochrane

**Fields**: 14

| Field | Type |
|-------|------|
| `abstract` | text |
| `authors` | array |
| `doi` | string |
| `groups` | array |
| `id` | string (review ID) |
| `keywords` | array |
| `pico_comparison` | string |
| `pico_intervention` | string |
| `pico_outcomes` | string |
| `pico_population` | string |
| `publication_year` | integer |
| `stage` | string |
| `status` | string (new/updated/withdrawn) |
| `title` | string |

---

### mol_raw.cochrane_reviews

_Same API as cochrane. See cochrane fields above._

---

### mol_raw.ct_gov_indication_stats

_ClinicalTrials.gov aggregate stats. Stored as search result counts by condition._

---

### mol_raw.dailymed

**Fields**: 10

| Field | Type |
|-------|------|
| `data` | array |
| `data[].published_date` | string |
| `data[].setid` | string |
| `data[].spl_version` | integer |
| `data[].title` | string |
| `metadata` | object |
| `metadata.current_page` | integer |
| `metadata.elements_per_page` | integer |
| `metadata.total_elements` | integer |
| `metadata.total_pages` | integer |

---

### mol_raw.drugbank

**Fields**: 50

| Field | Type |
|-------|------|
| `absorption` | text |
| `affected_organisms` | array |
| `atc_codes` | array |
| `atc_codes[].code` | string |
| `atc_codes[].description` | string |
| `carriers` | array |
| `cas_number` | string |
| `categories` | array |
| `categories[].category` | string |
| `categories[].mesh_id` | string |
| `clearance` | text |
| `description` | text |
| `dosages` | array |
| `dosages[].form` | string |
| `dosages[].route` | string |
| `dosages[].strength` | string |
| `drug_interactions` | array |
| `drug_interactions[].drugbank_id` | string |
| `drug_interactions[].name` | string |
| `drugbank_id` | string |
| `enzymes` | array |
| `external_identifiers` | array |
| `external_identifiers[].identifier` | string |
| `external_identifiers[].resource` | string |
| `external_links` | array |
| `food_interactions` | array |
| `groups` | array (approved/experimental/investigational) |
| `half_life` | text |
| `indication` | text |
| `mechanism_of_action` | text |
| `metabolism` | text |
| `name` | string |
| `patents` | array |
| `pharmacodynamics` | text |
| `protein_binding` | text |
| `route_of_elimination` | text |
| `state` | string |
| `targets` | array |
| `targets[].actions` | array |
| `targets[].id` | string |
| `targets[].name` | string |
| `targets[].organism` | string |
| `targets[].polypeptide` | object |
| `targets[].polypeptide.external_identifiers` | array |
| `targets[].polypeptide.gene_name` | string |
| `toxicity` | text |
| `transporters` | array |
| `type` | string (small molecule/biotech) |
| `unii` | string |
| `volume_of_distribution` | text |

---

### mol_raw.ema

**Fields**: 19

| Field | Type |
|-------|------|
| `accelerated_assessment` | boolean |
| `additional_monitoring` | boolean |
| `atc_code` | string |
| `authorization_date` | string |
| `authorization_status` | string (authorised/withdrawn/refused) |
| `biosimilar` | boolean |
| `condition_indication` | text |
| `conditional_approval` | boolean |
| `exceptional_circumstances` | boolean |
| `generic` | boolean |
| `inn` | string (international nonproprietary name) |
| `marketing_authorization_holder` | string |
| `medicine_name` | string |
| `orphan` | boolean |
| `patient_safety` | boolean |
| `product_number` | string |
| `revision_date` | string |
| `therapeutic_area` | string |
| `url` | string |

---

### mol_raw.epo_patents

**Fields**: 12

| Field | Type |
|-------|------|
| `abstract` | text |
| `bibliographic_data` | object |
| `bibliographic_data.applicants` | array |
| `bibliographic_data.classifications_ipcr` | array |
| `bibliographic_data.invention_title` | string |
| `bibliographic_data.inventors` | array |
| `bibliographic_data.priority_claims` | array |
| `publication_reference` | object |
| `publication_reference.document_id` | object |
| `publication_reference.document_id.country` | string |
| `publication_reference.document_id.doc_number` | string |
| `publication_reference.document_id.kind` | string |

---

### mol_raw.euipo_trademarks

**Fields**: 10

| Field | Type |
|-------|------|
| `expiry_date` | string |
| `filing_date` | string |
| `mark_status` | string |
| `mark_text` | string |
| `mark_type` | string |
| `nice_classification` | array (integers) |
| `owner_country` | string |
| `owner_name` | string |
| `registration_date` | string |
| `trademark_number` | string |

---

### mol_raw.hrsa_shortage_areas

**Fields**: 11

| Field | Type |
|-------|------|
| `county_name` | string |
| `designation_date` | string |
| `designation_type` | string (geographic/population/facility) |
| `fips_code` | string |
| `hpsa_discipline` | string (primary care/dental/mental health) |
| `hpsa_id` | string |
| `hpsa_name` | string |
| `hpsa_score` | integer |
| `hpsa_status` | string |
| `rural_status` | string |
| `state_name` | string |

---

### mol_raw.imgt

**Fields**: 13

| Field | Type |
|-------|------|
| `accession_number` | string |
| `allele_name` | string |
| `cdr1_end` | integer |
| `cdr1_start` | integer |
| `cdr2_end` | integer |
| `cdr2_start` | integer |
| `cdr3_end` | integer |
| `cdr3_start` | integer |
| `chain_type` | string (VH/VL/VK) |
| `functional_classification` | string |
| `gene_name` | string |
| `sequence` | text |
| `species` | string |

---

### mol_raw.kegg_drug

**Fields**: 7

| Field | Type |
|-------|------|
| `BRITE` | string (BRITE hierarchy classification) |
| `DBLINKS` | string (cross-references: CAS, PubChem, ChEBI, KEGG Compound) |
| `EFFICACY` | string (therapeutic category) |
| `ENTRY` | string (drug ID) |
| `NAME` | string (drug name) |
| `SEQUENCE` | string (amino acid sequence for biologics) |
| `TARGET` | string (target info) |

---

### mol_raw.npi_registry

**Fields**: 39

| Field | Type |
|-------|------|
| `addresses` | array |
| `addresses[].address_1` | string |
| `addresses[].address_2` | string |
| `addresses[].address_purpose` | string |
| `addresses[].address_type` | string |
| `addresses[].city` | string |
| `addresses[].country_code` | string |
| `addresses[].country_name` | string |
| `addresses[].fax_number` | string |
| `addresses[].postal_code` | string |
| `addresses[].state` | string |
| `addresses[].telephone_number` | string |
| `basic` | object |
| `basic.credential` | string |
| `basic.enumeration_date` | string |
| `basic.first_name` | string |
| `basic.last_name` | string |
| `basic.last_updated` | string |
| `basic.middle_name` | string |
| `basic.name_prefix` | string |
| `basic.name_suffix` | string |
| `basic.sex` | string |
| `basic.sole_proprietor` | string |
| `basic.status` | string |
| `created_epoch` | string |
| `endpoints` | array |
| `enumeration_type` | string |
| `identifiers` | array |
| `last_updated_epoch` | string |
| `number` | string |
| `other_names` | array |
| `practiceLocations` | array |
| `taxonomies` | array |
| `taxonomies[].code` | string |
| `taxonomies[].desc` | string |
| `taxonomies[].license` | string |
| `taxonomies[].primary` | boolean |
| `taxonomies[].state` | string |
| `taxonomies[].taxonomy_group` | string |

---

### mol_raw.orange_book

**Fields**: 17

| Field | Type |
|-------|------|
| `applicant` | string |
| `application_no` | string |
| `approval_date` | string |
| `dosage_form` | string |
| `drug_product_flag` | string |
| `drug_substance_flag` | string |
| `exclusivity_code` | string |
| `exclusivity_date` | string |
| `ingredient` | string |
| `patent_expire_date` | string |
| `patent_no` | string |
| `product_no` | string |
| `route` | string |
| `strength` | string |
| `te_code` | string (therapeutic equivalence) |
| `trade_name` | string |
| `type` | string (RX/OTC) |

---

### mol_raw.pdb_structures

_Same API as pdb (RCSB PDB). See pdb fields (283 fields)._

---

### mol_raw.pharmgkb

**Fields**: 21

| Field | Type |
|-------|------|
| `altNames` | object |
| `altNames.generic` | array |
| `altNames.mixture` | array |
| `altNames.trade` | array |
| `components` | array |
| `id` | string |
| `inChi` | string |
| `linkOuts` | array |
| `linkOuts[]._url` | string |
| `linkOuts[].name` | string |
| `linkOuts[].resource` | string |
| `linkOuts[].resourceId` | string |
| `metabolites` | array |
| `metabolites[].id` | string |
| `metabolites[].name` | string |
| `name` | string |
| `objCls` | string |
| `pediatric` | boolean |
| `smiles` | string |
| `types` | array |
| `version` | integer |

---

### mol_raw.rxnorm

**Fields**: 12

| Field | Type |
|-------|------|
| `drugGroup` | object |
| `drugGroup.conceptGroup` | array |
| `drugGroup.conceptGroup[].conceptProperties` | array |
| `drugGroup.conceptGroup[].conceptProperties[].language` | string |
| `drugGroup.conceptGroup[].conceptProperties[].name` | string |
| `drugGroup.conceptGroup[].conceptProperties[].rxcui` | string |
| `drugGroup.conceptGroup[].conceptProperties[].suppress` | string |
| `drugGroup.conceptGroup[].conceptProperties[].synonym` | string |
| `drugGroup.conceptGroup[].conceptProperties[].tty` | string |
| `drugGroup.conceptGroup[].conceptProperties[].umlscui` | string |
| `drugGroup.conceptGroup[].tty` | string |
| `drugGroup.name` | string |

---

### mol_raw.sider

**Fields**: 10

| Field | Type |
|-------|------|
| `frequency_description` | string |
| `frequency_lower_bound` | number |
| `frequency_upper_bound` | number |
| `meddra_id` | string |
| `meddra_type` | string (PT or LLT) |
| `placebo` | string |
| `side_effect_name` | string |
| `stitch_compound_id` | string |
| `stitch_flat_id` | string |
| `umls_concept_id` | string |

---

### mol_raw.tdc_admet

**Fields**: 5

| Field | Type |
|-------|------|
| `Drug` | string (drug name) |
| `Drug_ID` | string |
| `SMILES` | string |
| `Y` | number (property value) |
| `dataset_name` | string |

---

### mol_raw.ttd

**Fields**: 9

| Field | Type |
|-------|------|
| `Disease_Name` | string |
| `Drug_Name` | string |
| `Drug_Status` | string (approved/clinical trial/experimental) |
| `Gene_Name` | string |
| `ICD11` | string |
| `TTDID` | string |
| `Target_Name` | string |
| `Type` | string |
| `UniProt_ID` | string |

---

### mol_raw.uspto_ci

**Fields**: 6

| Field | Type |
|-------|------|
| `citation_category` | string |
| `citation_date` | string |
| `citation_sequence` | integer |
| `cited_patent` | string |
| `citing_patent` | string |
| `patent_number` | string |

---

### mol_raw.uspto_patents

**Fields**: 18

| Field | Type |
|-------|------|
| `assignees` | array |
| `assignees[].assignee_country` | string |
| `assignees[].assignee_individual_name_first` | string |
| `assignees[].assignee_organization` | string |
| `cpcs` | array |
| `cpcs[].cpc_group_id` | string |
| `cpcs[].cpc_subgroup_id` | string |
| `inventors` | array |
| `inventors[].inventor_country` | string |
| `inventors[].inventor_name_first` | string |
| `inventors[].inventor_name_last` | string |
| `patent_abstract` | text |
| `patent_date` | string |
| `patent_id` | string |
| `patent_num_cited_by_us_patents` | integer |
| `patent_num_claims` | integer |
| `patent_title` | string |
| `patent_type` | string |

---

### mol_raw.uspto_trademarks

**Fields**: 14

| Field | Type |
|-------|------|
| `attorney_name` | string |
| `design_search_code` | array |
| `filing_date` | string |
| `international_class` | array |
| `mark_drawing_code` | string |
| `mark_text` | string |
| `owner_address` | string |
| `owner_name` | string |
| `registration_date` | string |
| `registration_number` | string |
| `serial_number` | string |
| `status_code` | string |
| `status_date` | string |
| `us_class` | array |

---

### mol_raw.websearch

**Fields**: 10

| Field | Type |
|-------|------|
| `author` | string |
| `content` | text |
| `description` | string |
| `publishedAt` | string (ISO date) |
| `source` | object |
| `source.name` | string |
| `source.url` | string |
| `title` | string |
| `url` | string |
| `urlToImage` | string |

---

### mol_raw.who_gho

**Fields**: 23

| Field | Type |
|-------|------|
| `Comments` | string |
| `DataSourceDim` | null |
| `DataSourceDimType` | null |
| `Date` | string |
| `Dim1` | string |
| `Dim1Type` | string |
| `Dim2` | null |
| `Dim2Type` | null |
| `Dim3` | null |
| `Dim3Type` | null |
| `High` | number |
| `Id` | integer |
| `IndicatorCode` | string |
| `Low` | number |
| `NumericValue` | number |
| `SpatialDim` | string (country code) |
| `SpatialDimType` | string |
| `TimeDim` | string (year) |
| `TimeDimType` | string |
| `TimeDimensionBegin` | string |
| `TimeDimensionEnd` | string |
| `TimeDimensionValue` | string |
| `Value` | string |

---

### mol_raw.who_icd

**Fields**: 13

| Field | Type |
|-------|------|
| `blockId` | string |
| `browserUrl` | string |
| `child` | array (child entity URIs) |
| `classKind` | string |
| `codeRange` | string |
| `definition` | object |
| `exclusion` | array |
| `id` | string (entity URI) |
| `inclusion` | array |
| `parent` | array (parent entity URIs) |
| `title` | object |
| `title.@language` | string |
| `title.@value` | string |

---

### mol_raw.who_inn

**Fields**: 8

| Field | Type |
|-------|------|
| `atc_code` | string |
| `cas_number` | string |
| `chemical_name` | string |
| `inn_name` | string |
| `inn_number` | string (e.g. 9830) |
| `molecular_formula` | string |
| `recommended_list` | string (e.g. rl-79) |
| `year_published` | integer |

---


## Part 3: Populated Sources — Full Field Extraction from Database JSONB

These fields were extracted from actual `response_body` JSONB in the database.

### mol_raw.chembl (80 fields)

| Field Path | Type |
|------------|------|
| `molecules` | array |
| `molecules[].atc_classifications` | array |
| `molecules[].availability_type` | integer |
| `molecules[].biotherapeutic` | object |
| `molecules[].biotherapeutic.biocomponents` | array |
| `molecules[].biotherapeutic.biocomponents[].component_id` | integer |
| `molecules[].biotherapeutic.biocomponents[].component_type` | string |
| `molecules[].biotherapeutic.biocomponents[].description` | string |
| `molecules[].biotherapeutic.biocomponents[].organism` | null |
| `molecules[].biotherapeutic.biocomponents[].sequence` | text(long) |
| `molecules[].biotherapeutic.biocomponents[].tax_id` | null |
| `molecules[].biotherapeutic.description` | string |
| `molecules[].biotherapeutic.helm_notation` | null |
| `molecules[].biotherapeutic.molecule_chembl_id` | string |
| `molecules[].black_box_warning` | integer |
| `molecules[].chemical_probe` | integer |
| `molecules[].chirality` | integer |
| `molecules[].cross_references` | array |
| `molecules[].cross_references[].xref_id` | string |
| `molecules[].cross_references[].xref_name` | string |
| `molecules[].cross_references[].xref_src` | string |
| `molecules[].dosed_ingredient` | boolean |
| `molecules[].first_approval` | integer |
| `molecules[].first_in_class` | integer |
| `molecules[].helm_notation` | null |
| `molecules[].inorganic_flag` | integer |
| `molecules[].max_phase` | string |
| `molecules[].molecule_chembl_id` | string |
| `molecules[].molecule_hierarchy` | object |
| `molecules[].molecule_hierarchy.active_chembl_id` | string |
| `molecules[].molecule_hierarchy.molecule_chembl_id` | string |
| `molecules[].molecule_hierarchy.parent_chembl_id` | string |
| `molecules[].molecule_properties` | null |
| `molecules[].molecule_properties.alogp` | string |
| `molecules[].molecule_properties.aromatic_rings` | integer |
| `molecules[].molecule_properties.full_molformula` | string |
| `molecules[].molecule_properties.full_mwt` | string |
| `molecules[].molecule_properties.hba` | integer |
| `molecules[].molecule_properties.hbd` | integer |
| `molecules[].molecule_properties.heavy_atoms` | integer |
| `molecules[].molecule_properties.mw_freebase` | string |
| `molecules[].molecule_properties.np_likeness_score` | string |
| `molecules[].molecule_properties.num_ro5_violations` | integer |
| `molecules[].molecule_properties.psa` | string |
| `molecules[].molecule_properties.qed_weighted` | string |
| `molecules[].molecule_properties.ro3_pass` | string |
| `molecules[].molecule_properties.rtb` | integer |
| `molecules[].molecule_structures` | null |
| `molecules[].molecule_structures.canonical_smiles` | string |
| `molecules[].molecule_structures.molfile` | text(long) |
| `molecules[].molecule_structures.standard_inchi` | string |
| `molecules[].molecule_structures.standard_inchi_key` | string |
| `molecules[].molecule_synonyms` | array |
| `molecules[].molecule_synonyms[].molecule_synonym` | string |
| `molecules[].molecule_synonyms[].syn_type` | string |
| `molecules[].molecule_synonyms[].synonyms` | string |
| `molecules[].molecule_type` | string |
| `molecules[].natural_product` | integer |
| `molecules[].oral` | boolean |
| `molecules[].orphan` | integer |
| `molecules[].parenteral` | boolean |
| `molecules[].polymer_flag` | integer |
| `molecules[].pref_name` | string |
| `molecules[].prodrug` | integer |
| `molecules[].score` | number |
| `molecules[].structure_type` | string |
| `molecules[].therapeutic_flag` | boolean |
| `molecules[].topical` | boolean |
| `molecules[].usan_stem` | string |
| `molecules[].usan_stem_definition` | string |
| `molecules[].usan_substem` | string |
| `molecules[].usan_year` | integer |
| `molecules[].veterinary` | integer |
| `molecules[].withdrawn_flag` | boolean |
| `page_meta` | object |
| `page_meta.limit` | integer |
| `page_meta.next` | null |
| `page_meta.offset` | integer |
| `page_meta.previous` | null |
| `page_meta.total_count` | integer |

---

### mol_raw.clinicaltrials (292 fields)

| Field Path | Type |
|------------|------|
| `derivedSection` | object |
| `derivedSection.conditionBrowseModule` | object |
| `derivedSection.conditionBrowseModule.ancestors` | array |
| `derivedSection.conditionBrowseModule.ancestors[].id` | string |
| `derivedSection.conditionBrowseModule.ancestors[].term` | string |
| `derivedSection.conditionBrowseModule.meshes` | array |
| `derivedSection.conditionBrowseModule.meshes[].id` | string |
| `derivedSection.conditionBrowseModule.meshes[].term` | string |
| `derivedSection.interventionBrowseModule` | object |
| `derivedSection.interventionBrowseModule.meshes` | array |
| `derivedSection.interventionBrowseModule.meshes[].id` | string |
| `derivedSection.interventionBrowseModule.meshes[].term` | string |
| `derivedSection.miscInfoModule` | object |
| `derivedSection.miscInfoModule.submissionTracking` | object |
| `derivedSection.miscInfoModule.submissionTracking.firstMcpInfo` | object |
| `derivedSection.miscInfoModule.submissionTracking.firstMcpInfo.postDateStruct` | object |
| `derivedSection.miscInfoModule.versionHolder` | string |
| `documentSection` | object |
| `documentSection.largeDocumentModule` | object |
| `documentSection.largeDocumentModule.largeDocs` | array |
| `documentSection.largeDocumentModule.largeDocs[].date` | string |
| `documentSection.largeDocumentModule.largeDocs[].filename` | string |
| `documentSection.largeDocumentModule.largeDocs[].hasIcf` | boolean |
| `documentSection.largeDocumentModule.largeDocs[].hasProtocol` | boolean |
| `documentSection.largeDocumentModule.largeDocs[].hasSap` | boolean |
| `documentSection.largeDocumentModule.largeDocs[].label` | string |
| `documentSection.largeDocumentModule.largeDocs[].size` | integer |
| `documentSection.largeDocumentModule.largeDocs[].typeAbbrev` | string |
| `documentSection.largeDocumentModule.largeDocs[].uploadDate` | string |
| `hasResults` | boolean |
| `protocolSection` | object |
| `protocolSection.armsInterventionsModule` | object |
| `protocolSection.armsInterventionsModule.armGroups` | array |
| `protocolSection.armsInterventionsModule.armGroups[].description` | string |
| `protocolSection.armsInterventionsModule.armGroups[].interventionNames` | array |
| `protocolSection.armsInterventionsModule.armGroups[].label` | string |
| `protocolSection.armsInterventionsModule.armGroups[].type` | string |
| `protocolSection.armsInterventionsModule.interventions` | array |
| `protocolSection.armsInterventionsModule.interventions[].armGroupLabels` | array |
| `protocolSection.armsInterventionsModule.interventions[].description` | string |
| `protocolSection.armsInterventionsModule.interventions[].name` | string |
| `protocolSection.armsInterventionsModule.interventions[].otherNames` | array |
| `protocolSection.armsInterventionsModule.interventions[].type` | string |
| `protocolSection.conditionsModule` | object |
| `protocolSection.conditionsModule.conditions` | array |
| `protocolSection.conditionsModule.keywords` | array |
| `protocolSection.contactsLocationsModule` | object |
| `protocolSection.contactsLocationsModule.centralContacts` | array |
| `protocolSection.contactsLocationsModule.centralContacts[].email` | string |
| `protocolSection.contactsLocationsModule.centralContacts[].name` | string |
| `protocolSection.contactsLocationsModule.centralContacts[].phone` | string |
| `protocolSection.contactsLocationsModule.centralContacts[].phoneExt` | string |
| `protocolSection.contactsLocationsModule.centralContacts[].role` | string |
| `protocolSection.contactsLocationsModule.locations` | array |
| `protocolSection.contactsLocationsModule.locations[].city` | string |
| `protocolSection.contactsLocationsModule.locations[].contacts` | array |
| `protocolSection.contactsLocationsModule.locations[].contacts[].email` | string |
| `protocolSection.contactsLocationsModule.locations[].contacts[].name` | string |
| `protocolSection.contactsLocationsModule.locations[].contacts[].phone` | string |
| `protocolSection.contactsLocationsModule.locations[].contacts[].role` | string |
| `protocolSection.contactsLocationsModule.locations[].country` | string |
| `protocolSection.contactsLocationsModule.locations[].facility` | string |
| `protocolSection.contactsLocationsModule.locations[].geoPoint` | object |
| `protocolSection.contactsLocationsModule.locations[].geoPoint.lat` | number |
| `protocolSection.contactsLocationsModule.locations[].geoPoint.lon` | number |
| `protocolSection.contactsLocationsModule.locations[].state` | string |
| `protocolSection.contactsLocationsModule.locations[].status` | string |
| `protocolSection.contactsLocationsModule.locations[].zip` | string |
| `protocolSection.contactsLocationsModule.overallOfficials` | array |
| `protocolSection.contactsLocationsModule.overallOfficials[].affiliation` | string |
| `protocolSection.contactsLocationsModule.overallOfficials[].name` | string |
| `protocolSection.contactsLocationsModule.overallOfficials[].role` | string |
| `protocolSection.descriptionModule` | object |
| `protocolSection.descriptionModule.briefSummary` | text(long) |
| `protocolSection.descriptionModule.detailedDescription` | text(long) |
| `protocolSection.designModule` | object |
| `protocolSection.designModule.bioSpec` | object |
| `protocolSection.designModule.bioSpec.description` | string |
| `protocolSection.designModule.bioSpec.retention` | string |
| `protocolSection.designModule.designInfo` | object |
| `protocolSection.designModule.designInfo.allocation` | string |
| `protocolSection.designModule.designInfo.interventionModel` | string |
| `protocolSection.designModule.designInfo.interventionModelDescription` | string |
| `protocolSection.designModule.designInfo.maskingInfo` | object |
| `protocolSection.designModule.designInfo.maskingInfo.masking` | string |
| `protocolSection.designModule.designInfo.maskingInfo.whoMasked` | array |
| `protocolSection.designModule.designInfo.observationalModel` | string |
| `protocolSection.designModule.designInfo.primaryPurpose` | string |
| `protocolSection.designModule.designInfo.timePerspective` | string |
| `protocolSection.designModule.enrollmentInfo` | object |
| `protocolSection.designModule.enrollmentInfo.count` | integer |
| `protocolSection.designModule.enrollmentInfo.type` | string |
| `protocolSection.designModule.patientRegistry` | boolean |
| `protocolSection.designModule.phases` | array |
| `protocolSection.designModule.studyType` | string |
| `protocolSection.eligibilityModule` | object |
| `protocolSection.eligibilityModule.eligibilityCriteria` | text(long) |
| `protocolSection.eligibilityModule.healthyVolunteers` | boolean |
| `protocolSection.eligibilityModule.maximumAge` | string |
| `protocolSection.eligibilityModule.minimumAge` | string |
| `protocolSection.eligibilityModule.samplingMethod` | string |
| `protocolSection.eligibilityModule.sex` | string |
| `protocolSection.eligibilityModule.stdAges` | array |
| `protocolSection.eligibilityModule.studyPopulation` | string |
| `protocolSection.identificationModule` | object |
| `protocolSection.identificationModule.acronym` | string |
| `protocolSection.identificationModule.briefTitle` | string |
| `protocolSection.identificationModule.nctId` | string |
| `protocolSection.identificationModule.officialTitle` | text(long) |
| `protocolSection.identificationModule.orgStudyIdInfo` | object |
| `protocolSection.identificationModule.orgStudyIdInfo.id` | string |
| `protocolSection.identificationModule.organization` | object |
| `protocolSection.identificationModule.organization.class` | string |
| `protocolSection.identificationModule.organization.fullName` | string |
| `protocolSection.identificationModule.secondaryIdInfos` | array |
| `protocolSection.identificationModule.secondaryIdInfos[].domain` | string |
| `protocolSection.identificationModule.secondaryIdInfos[].id` | string |
| `protocolSection.identificationModule.secondaryIdInfos[].type` | string |
| `protocolSection.ipdSharingStatementModule` | object |
| `protocolSection.ipdSharingStatementModule.accessCriteria` | text(long) |
| `protocolSection.ipdSharingStatementModule.description` | string |
| `protocolSection.ipdSharingStatementModule.infoTypes` | array |
| `protocolSection.ipdSharingStatementModule.ipdSharing` | string |
| `protocolSection.ipdSharingStatementModule.timeFrame` | text(long) |
| `protocolSection.ipdSharingStatementModule.url` | string |
| `protocolSection.outcomesModule` | object |
| `protocolSection.outcomesModule.primaryOutcomes` | array |
| `protocolSection.outcomesModule.primaryOutcomes[].description` | text(long) |
| `protocolSection.outcomesModule.primaryOutcomes[].measure` | string |
| `protocolSection.outcomesModule.primaryOutcomes[].timeFrame` | string |
| `protocolSection.outcomesModule.secondaryOutcomes` | array |
| `protocolSection.outcomesModule.secondaryOutcomes[].description` | text(long) |
| `protocolSection.outcomesModule.secondaryOutcomes[].measure` | string |
| `protocolSection.outcomesModule.secondaryOutcomes[].timeFrame` | string |
| `protocolSection.oversightModule` | object |
| `protocolSection.oversightModule.isFdaRegulatedDevice` | boolean |
| `protocolSection.oversightModule.isFdaRegulatedDrug` | boolean |
| `protocolSection.oversightModule.isUsExport` | boolean |
| `protocolSection.oversightModule.oversightHasDmc` | boolean |
| `protocolSection.referencesModule` | object |
| `protocolSection.referencesModule.references` | array |
| `protocolSection.referencesModule.references[].citation` | text(long) |
| `protocolSection.referencesModule.references[].pmid` | string |
| `protocolSection.referencesModule.references[].type` | string |
| `protocolSection.referencesModule.seeAlsoLinks` | array |
| `protocolSection.referencesModule.seeAlsoLinks[].label` | string |
| `protocolSection.referencesModule.seeAlsoLinks[].url` | string |
| `protocolSection.sponsorCollaboratorsModule` | object |
| `protocolSection.sponsorCollaboratorsModule.collaborators` | array |
| `protocolSection.sponsorCollaboratorsModule.collaborators[].class` | string |
| `protocolSection.sponsorCollaboratorsModule.collaborators[].name` | string |
| `protocolSection.sponsorCollaboratorsModule.leadSponsor` | object |
| `protocolSection.sponsorCollaboratorsModule.leadSponsor.class` | string |
| `protocolSection.sponsorCollaboratorsModule.leadSponsor.name` | string |
| `protocolSection.sponsorCollaboratorsModule.responsibleParty` | object |
| `protocolSection.sponsorCollaboratorsModule.responsibleParty.investigatorAffiliation` | string |
| `protocolSection.sponsorCollaboratorsModule.responsibleParty.investigatorFullName` | string |
| `protocolSection.sponsorCollaboratorsModule.responsibleParty.investigatorTitle` | string |
| `protocolSection.sponsorCollaboratorsModule.responsibleParty.type` | string |
| `protocolSection.statusModule` | object |
| `protocolSection.statusModule.completionDateStruct` | object |
| `protocolSection.statusModule.completionDateStruct.date` | string |
| `protocolSection.statusModule.completionDateStruct.type` | string |
| `protocolSection.statusModule.expandedAccessInfo` | object |
| `protocolSection.statusModule.expandedAccessInfo.hasExpandedAccess` | boolean |
| `protocolSection.statusModule.lastKnownStatus` | string |
| `protocolSection.statusModule.lastUpdatePostDateStruct` | object |
| `protocolSection.statusModule.lastUpdatePostDateStruct.date` | string |
| `protocolSection.statusModule.lastUpdatePostDateStruct.type` | string |
| `protocolSection.statusModule.lastUpdateSubmitDate` | string |
| `protocolSection.statusModule.overallStatus` | string |
| `protocolSection.statusModule.primaryCompletionDateStruct` | object |
| `protocolSection.statusModule.primaryCompletionDateStruct.date` | string |
| `protocolSection.statusModule.primaryCompletionDateStruct.type` | string |
| `protocolSection.statusModule.resultsFirstPostDateStruct` | object |
| `protocolSection.statusModule.resultsFirstPostDateStruct.date` | string |
| `protocolSection.statusModule.resultsFirstPostDateStruct.type` | string |
| `protocolSection.statusModule.resultsFirstSubmitDate` | string |
| `protocolSection.statusModule.resultsFirstSubmitQcDate` | string |
| `protocolSection.statusModule.startDateStruct` | object |
| `protocolSection.statusModule.startDateStruct.date` | string |
| `protocolSection.statusModule.startDateStruct.type` | string |
| `protocolSection.statusModule.statusVerifiedDate` | string |
| `protocolSection.statusModule.studyFirstPostDateStruct` | object |
| `protocolSection.statusModule.studyFirstPostDateStruct.date` | string |
| `protocolSection.statusModule.studyFirstPostDateStruct.type` | string |
| `protocolSection.statusModule.studyFirstSubmitDate` | string |
| `protocolSection.statusModule.studyFirstSubmitQcDate` | string |
| `resultsSection` | object |
| `resultsSection.adverseEventsModule` | object |
| `resultsSection.adverseEventsModule.description` | text(long) |
| `resultsSection.adverseEventsModule.eventGroups` | array |
| `resultsSection.adverseEventsModule.eventGroups[].deathsNumAffected` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].deathsNumAtRisk` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].description` | string |
| `resultsSection.adverseEventsModule.eventGroups[].id` | string |
| `resultsSection.adverseEventsModule.eventGroups[].otherNumAffected` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].otherNumAtRisk` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].seriousNumAffected` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].seriousNumAtRisk` | integer |
| `resultsSection.adverseEventsModule.eventGroups[].title` | string |
| `resultsSection.adverseEventsModule.frequencyThreshold` | string |
| `resultsSection.adverseEventsModule.otherEvents` | array |
| `resultsSection.adverseEventsModule.otherEvents[].assessmentType` | string |
| `resultsSection.adverseEventsModule.otherEvents[].organSystem` | string |
| `resultsSection.adverseEventsModule.otherEvents[].sourceVocabulary` | string |
| `resultsSection.adverseEventsModule.otherEvents[].stats` | array |
| `resultsSection.adverseEventsModule.otherEvents[].stats[].groupId` | string |
| `resultsSection.adverseEventsModule.otherEvents[].stats[].numAffected` | integer |
| `resultsSection.adverseEventsModule.otherEvents[].stats[].numAtRisk` | integer |
| `resultsSection.adverseEventsModule.otherEvents[].stats[].numEvents` | integer |
| `resultsSection.adverseEventsModule.otherEvents[].term` | string |
| `resultsSection.adverseEventsModule.seriousEvents` | array |
| `resultsSection.adverseEventsModule.seriousEvents[].assessmentType` | string |
| `resultsSection.adverseEventsModule.seriousEvents[].organSystem` | string |
| `resultsSection.adverseEventsModule.seriousEvents[].sourceVocabulary` | string |
| `resultsSection.adverseEventsModule.seriousEvents[].stats` | array |
| `resultsSection.adverseEventsModule.seriousEvents[].stats[].groupId` | string |
| `resultsSection.adverseEventsModule.seriousEvents[].stats[].numAffected` | integer |
| `resultsSection.adverseEventsModule.seriousEvents[].stats[].numAtRisk` | integer |
| `resultsSection.adverseEventsModule.seriousEvents[].stats[].numEvents` | integer |
| `resultsSection.adverseEventsModule.seriousEvents[].term` | string |
| `resultsSection.adverseEventsModule.timeFrame` | string |
| `resultsSection.baselineCharacteristicsModule` | object |
| `resultsSection.baselineCharacteristicsModule.denoms` | array |
| `resultsSection.baselineCharacteristicsModule.denoms[].counts` | array |
| `resultsSection.baselineCharacteristicsModule.denoms[].counts[].groupId` | string |
| `resultsSection.baselineCharacteristicsModule.denoms[].counts[].value` | string |
| `resultsSection.baselineCharacteristicsModule.denoms[].units` | string |
| `resultsSection.baselineCharacteristicsModule.groups` | array |
| `resultsSection.baselineCharacteristicsModule.groups[].description` | string |
| `resultsSection.baselineCharacteristicsModule.groups[].id` | string |
| `resultsSection.baselineCharacteristicsModule.groups[].title` | string |
| `resultsSection.baselineCharacteristicsModule.measures` | array |
| `resultsSection.baselineCharacteristicsModule.measures[].classes` | array |
| `resultsSection.baselineCharacteristicsModule.measures[].classes[].categories` | array |
| `resultsSection.baselineCharacteristicsModule.measures[].dispersionType` | string |
| `resultsSection.baselineCharacteristicsModule.measures[].paramType` | string |
| `resultsSection.baselineCharacteristicsModule.measures[].title` | string |
| `resultsSection.baselineCharacteristicsModule.measures[].unitOfMeasure` | string |
| `resultsSection.baselineCharacteristicsModule.populationDescription` | text(long) |
| `resultsSection.moreInfoModule` | object |
| `resultsSection.moreInfoModule.certainAgreement` | object |
| `resultsSection.moreInfoModule.certainAgreement.otherDetails` | text(long) |
| `resultsSection.moreInfoModule.certainAgreement.piSponsorEmployee` | boolean |
| `resultsSection.moreInfoModule.certainAgreement.restrictionType` | string |
| `resultsSection.moreInfoModule.certainAgreement.restrictiveAgreement` | boolean |
| `resultsSection.moreInfoModule.pointOfContact` | object |
| `resultsSection.moreInfoModule.pointOfContact.email` | string |
| `resultsSection.moreInfoModule.pointOfContact.organization` | string |
| `resultsSection.moreInfoModule.pointOfContact.phone` | string |
| `resultsSection.moreInfoModule.pointOfContact.title` | string |
| `resultsSection.outcomeMeasuresModule` | object |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[].groupIds` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[].nonInferiorityType` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[].pValue` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[].statisticalMethod` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].classes` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].classes[].categories` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].denoms` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].denoms[].counts` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].denoms[].units` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].description` | text(long) |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].dispersionType` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].groups` | array |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].groups[].description` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].groups[].id` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].groups[].title` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].paramType` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].populationDescription` | text(long) |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].reportingStatus` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].timeFrame` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].title` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].type` | string |
| `resultsSection.outcomeMeasuresModule.outcomeMeasures[].unitOfMeasure` | string |
| `resultsSection.participantFlowModule` | object |
| `resultsSection.participantFlowModule.groups` | array |
| `resultsSection.participantFlowModule.groups[].description` | string |
| `resultsSection.participantFlowModule.groups[].id` | string |
| `resultsSection.participantFlowModule.groups[].title` | string |
| `resultsSection.participantFlowModule.periods` | array |
| `resultsSection.participantFlowModule.periods[].dropWithdraws` | array |
| `resultsSection.participantFlowModule.periods[].dropWithdraws[].reasons` | array |
| `resultsSection.participantFlowModule.periods[].dropWithdraws[].type` | string |
| `resultsSection.participantFlowModule.periods[].milestones` | array |
| `resultsSection.participantFlowModule.periods[].milestones[].achievements` | array |
| `resultsSection.participantFlowModule.periods[].milestones[].type` | string |
| `resultsSection.participantFlowModule.periods[].title` | string |
| `resultsSection.participantFlowModule.preAssignmentDetails` | text(long) |
| `resultsSection.participantFlowModule.recruitmentDetails` | text(long) |

---

### mol_raw.cms_open_payments (91 fields)

| Field Path | Type |
|------------|------|
| `applicable_manufacturer_or_applicable_gpo_making_payment_country` | string |
| `applicable_manufacturer_or_applicable_gpo_making_payment_id` | string |
| `applicable_manufacturer_or_applicable_gpo_making_payment_name` | string |
| `applicable_manufacturer_or_applicable_gpo_making_payment_state` | string |
| `associated_device_or_medical_supply_pdi_1` | string |
| `associated_device_or_medical_supply_pdi_2` | string |
| `associated_device_or_medical_supply_pdi_3` | string |
| `associated_device_or_medical_supply_pdi_4` | string |
| `associated_device_or_medical_supply_pdi_5` | string |
| `associated_drug_or_biological_ndc_1` | string |
| `associated_drug_or_biological_ndc_2` | string |
| `associated_drug_or_biological_ndc_3` | string |
| `associated_drug_or_biological_ndc_4` | string |
| `associated_drug_or_biological_ndc_5` | string |
| `change_type` | string |
| `charity_indicator` | string |
| `city_of_travel` | string |
| `contextual_information` | string |
| `country_of_travel` | string |
| `covered_or_noncovered_indicator_1` | string |
| `covered_or_noncovered_indicator_2` | string |
| `covered_or_noncovered_indicator_3` | string |
| `covered_or_noncovered_indicator_4` | string |
| `covered_or_noncovered_indicator_5` | string |
| `covered_recipient_first_name` | string |
| `covered_recipient_last_name` | string |
| `covered_recipient_license_state_code1` | string |
| `covered_recipient_license_state_code2` | string |
| `covered_recipient_license_state_code3` | string |
| `covered_recipient_license_state_code4` | string |
| `covered_recipient_license_state_code5` | string |
| `covered_recipient_middle_name` | string |
| `covered_recipient_name_suffix` | string |
| `covered_recipient_npi` | string |
| `covered_recipient_primary_type_1` | string |
| `covered_recipient_primary_type_2` | string |
| `covered_recipient_primary_type_3` | string |
| `covered_recipient_primary_type_4` | string |
| `covered_recipient_primary_type_5` | string |
| `covered_recipient_primary_type_6` | string |
| `covered_recipient_profile_id` | string |
| `covered_recipient_specialty_1` | string |
| `covered_recipient_specialty_2` | string |
| `covered_recipient_specialty_3` | string |
| `covered_recipient_specialty_4` | string |
| `covered_recipient_specialty_5` | string |
| `covered_recipient_specialty_6` | string |
| `covered_recipient_type` | string |
| `date_of_payment` | string |
| `delay_in_publication_indicator` | string |
| `dispute_status_for_publication` | string |
| `form_of_payment_or_transfer_of_value` | string |
| `indicate_drug_or_biological_or_device_or_medical_supply_1` | string |
| `indicate_drug_or_biological_or_device_or_medical_supply_2` | string |
| `indicate_drug_or_biological_or_device_or_medical_supply_3` | string |
| `indicate_drug_or_biological_or_device_or_medical_supply_4` | string |
| `indicate_drug_or_biological_or_device_or_medical_supply_5` | string |
| `name_of_drug_or_biological_or_device_or_medical_supply_1` | string |
| `name_of_drug_or_biological_or_device_or_medical_supply_2` | string |
| `name_of_drug_or_biological_or_device_or_medical_supply_3` | string |
| `name_of_drug_or_biological_or_device_or_medical_supply_4` | string |
| `name_of_drug_or_biological_or_device_or_medical_supply_5` | string |
| `name_of_third_party_entity_receiving_payment_or_transfer_of_ccfc` | string |
| `nature_of_payment_or_transfer_of_value` | string |
| `number_of_payments_included_in_total_amount` | string |
| `payment_publication_date` | string |
| `physician_ownership_indicator` | string |
| `product_category_or_therapeutic_area_1` | string |
| `product_category_or_therapeutic_area_2` | string |
| `product_category_or_therapeutic_area_3` | string |
| `product_category_or_therapeutic_area_4` | string |
| `product_category_or_therapeutic_area_5` | string |
| `program_year` | string |
| `recipient_city` | string |
| `recipient_country` | string |
| `recipient_postal_code` | string |
| `recipient_primary_business_street_address_line1` | string |
| `recipient_primary_business_street_address_line2` | string |
| `recipient_province` | string |
| `recipient_state` | string |
| `recipient_zip_code` | string |
| `record_id` | string |
| `related_product_indicator` | string |
| `state_of_travel` | string |
| `submitting_applicable_manufacturer_or_applicable_gpo_name` | string |
| `teaching_hospital_ccn` | string |
| `teaching_hospital_id` | string |
| `teaching_hospital_name` | string |
| `third_party_equals_covered_recipient_indicator` | string |
| `third_party_payment_recipient_indicator` | string |
| `total_amount_of_payment_usdollars` | string |

---

### mol_raw.fda_drugsfda (44 fields)

| Field Path | Type |
|------------|------|
| `application_number` | string |
| `openfda` | object |
| `openfda.application_number` | array |
| `openfda.brand_name` | array |
| `openfda.generic_name` | array |
| `openfda.manufacturer_name` | array |
| `openfda.nui` | array |
| `openfda.package_ndc` | array |
| `openfda.pharm_class_cs` | array |
| `openfda.pharm_class_epc` | array |
| `openfda.pharm_class_moa` | array |
| `openfda.product_ndc` | array |
| `openfda.product_type` | array |
| `openfda.route` | array |
| `openfda.rxcui` | array |
| `openfda.spl_id` | array |
| `openfda.spl_set_id` | array |
| `openfda.substance_name` | array |
| `openfda.unii` | array |
| `products` | array |
| `products[].active_ingredients` | array |
| `products[].active_ingredients[].name` | string |
| `products[].active_ingredients[].strength` | string |
| `products[].brand_name` | string |
| `products[].dosage_form` | string |
| `products[].marketing_status` | string |
| `products[].product_number` | string |
| `products[].reference_drug` | string |
| `products[].reference_standard` | string |
| `products[].route` | string |
| `sponsor_name` | string |
| `submissions` | array |
| `submissions[].application_docs` | array |
| `submissions[].application_docs[].date` | string |
| `submissions[].application_docs[].id` | string |
| `submissions[].application_docs[].type` | string |
| `submissions[].application_docs[].url` | string |
| `submissions[].review_priority` | string |
| `submissions[].submission_class_code` | string |
| `submissions[].submission_class_code_description` | string |
| `submissions[].submission_number` | string |
| `submissions[].submission_status` | string |
| `submissions[].submission_status_date` | string |
| `submissions[].submission_type` | string |

---

### mol_raw.kegg (1 fields)

| Field Path | Type |
|------------|------|
| `text` | text(long) |

---

### mol_raw.nice_hta (1 fields)

| Field Path | Type |
|------------|------|
| `html_size` | integer |

---

### mol_raw.nih_reporter (11 fields)

| Field Path | Type |
|------------|------|
| `meta` | object |
| `meta.limit` | integer |
| `meta.offset` | integer |
| `meta.properties` | object |
| `meta.properties.URL` | string |
| `meta.search_id` | string |
| `meta.sort_field` | null |
| `meta.sort_order` | string |
| `meta.sorted_by_relevance` | boolean |
| `meta.total` | integer |
| `results` | array |

---

### mol_raw.openalex (215 fields)

| Field Path | Type |
|------------|------|
| `abstract_inverted_index` | object |
| `apc_list` | null |
| `apc_list.currency` | string |
| `apc_list.value` | integer |
| `apc_list.value_usd` | integer |
| `apc_paid` | null |
| `authorships` | array |
| `authorships[].affiliations` | array |
| `authorships[].affiliations[].institution_ids` | array |
| `authorships[].affiliations[].raw_affiliation_string` | string |
| `authorships[].author` | object |
| `authorships[].author.display_name` | string |
| `authorships[].author.id` | string |
| `authorships[].author.orcid` | string |
| `authorships[].author_position` | string |
| `authorships[].countries` | array |
| `authorships[].institutions` | array |
| `authorships[].institutions[].country_code` | string |
| `authorships[].institutions[].display_name` | string |
| `authorships[].institutions[].id` | string |
| `authorships[].institutions[].lineage` | array |
| `authorships[].institutions[].ror` | string |
| `authorships[].institutions[].type` | string |
| `authorships[].is_corresponding` | boolean |
| `authorships[].raw_affiliation_strings` | array |
| `authorships[].raw_author_name` | string |
| `awards` | array |
| `awards[].display_name` | null |
| `awards[].funder_award_id` | string |
| `awards[].funder_display_name` | string |
| `awards[].funder_id` | string |
| `awards[].id` | string |
| `best_oa_location` | null |
| `best_oa_location.id` | string |
| `best_oa_location.is_accepted` | boolean |
| `best_oa_location.is_oa` | boolean |
| `best_oa_location.is_published` | boolean |
| `best_oa_location.landing_page_url` | string |
| `best_oa_location.license` | null |
| `best_oa_location.license_id` | null |
| `best_oa_location.pdf_url` | string |
| `best_oa_location.raw_source_name` | string |
| `best_oa_location.raw_type` | string |
| `best_oa_location.source` | object |
| `best_oa_location.source.display_name` | string |
| `best_oa_location.source.host_organization` | string |
| `best_oa_location.source.host_organization_lineage` | array |
| `best_oa_location.source.host_organization_lineage_names` | array |
| `best_oa_location.source.host_organization_name` | string |
| `best_oa_location.source.id` | string |
| `best_oa_location.source.is_core` | boolean |
| `best_oa_location.source.is_in_doaj` | boolean |
| `best_oa_location.source.is_oa` | boolean |
| `best_oa_location.source.issn` | array |
| `best_oa_location.source.issn_l` | string |
| `best_oa_location.source.type` | string |
| `best_oa_location.version` | string |
| `biblio` | object |
| `biblio.first_page` | null |
| `biblio.issue` | null |
| `biblio.last_page` | null |
| `biblio.volume` | null |
| `citation_normalized_percentile` | object |
| `citation_normalized_percentile.is_in_top_10_percent` | boolean |
| `citation_normalized_percentile.is_in_top_1_percent` | boolean |
| `citation_normalized_percentile.value` | number |
| `cited_by_count` | integer |
| `cited_by_percentile_year` | object |
| `cited_by_percentile_year.max` | integer |
| `cited_by_percentile_year.min` | integer |
| `concepts` | array |
| `concepts[].display_name` | string |
| `concepts[].id` | string |
| `concepts[].level` | integer |
| `concepts[].score` | number |
| `concepts[].wikidata` | string |
| `content_urls` | null |
| `content_urls.grobid_xml` | string |
| `content_urls.pdf` | string |
| `corresponding_author_ids` | array |
| `corresponding_institution_ids` | array |
| `countries_distinct_count` | integer |
| `counts_by_year` | array |
| `counts_by_year[].cited_by_count` | integer |
| `counts_by_year[].year` | integer |
| `created_date` | string |
| `display_name` | string |
| `doi` | null |
| `funders` | array |
| `funders[].display_name` | string |
| `funders[].id` | string |
| `funders[].ror` | string |
| `fwci` | number |
| `has_content` | object |
| `has_content.grobid_xml` | boolean |
| `has_content.pdf` | boolean |
| `has_fulltext` | boolean |
| `id` | string |
| `ids` | object |
| `ids.doi` | string |
| `ids.mag` | string |
| `ids.openalex` | string |
| `ids.pmid` | string |
| `indexed_in` | array |
| `institutions` | array |
| `institutions_distinct_count` | integer |
| `is_paratext` | boolean |
| `is_retracted` | boolean |
| `is_xpac` | boolean |
| `keywords` | array |
| `keywords[].display_name` | string |
| `keywords[].id` | string |
| `keywords[].score` | number |
| `language` | string |
| `locations` | array |
| `locations[].id` | string |
| `locations[].is_accepted` | boolean |
| `locations[].is_oa` | boolean |
| `locations[].is_published` | boolean |
| `locations[].landing_page_url` | null |
| `locations[].license` | null |
| `locations[].license_id` | null |
| `locations[].pdf_url` | null |
| `locations[].raw_source_name` | null |
| `locations[].raw_type` | string |
| `locations[].source` | object |
| `locations[].source.display_name` | string |
| `locations[].source.host_organization` | string |
| `locations[].source.host_organization_lineage` | array |
| `locations[].source.host_organization_lineage_names` | array |
| `locations[].source.host_organization_name` | string |
| `locations[].source.id` | string |
| `locations[].source.is_core` | boolean |
| `locations[].source.is_in_doaj` | boolean |
| `locations[].source.is_oa` | boolean |
| `locations[].source.issn` | null |
| `locations[].source.issn_l` | null |
| `locations[].source.type` | string |
| `locations[].version` | string |
| `locations_count` | integer |
| `mesh` | array |
| `mesh[].descriptor_name` | string |
| `mesh[].descriptor_ui` | string |
| `mesh[].is_major_topic` | boolean |
| `mesh[].qualifier_name` | string |
| `mesh[].qualifier_ui` | string |
| `open_access` | object |
| `open_access.any_repository_has_fulltext` | boolean |
| `open_access.is_oa` | boolean |
| `open_access.oa_status` | string |
| `open_access.oa_url` | null |
| `primary_location` | object |
| `primary_location.id` | string |
| `primary_location.is_accepted` | boolean |
| `primary_location.is_oa` | boolean |
| `primary_location.is_published` | boolean |
| `primary_location.landing_page_url` | null |
| `primary_location.license` | null |
| `primary_location.license_id` | null |
| `primary_location.pdf_url` | null |
| `primary_location.raw_source_name` | null |
| `primary_location.raw_type` | string |
| `primary_location.source` | object |
| `primary_location.source.display_name` | string |
| `primary_location.source.host_organization` | string |
| `primary_location.source.host_organization_lineage` | array |
| `primary_location.source.host_organization_lineage_names` | array |
| `primary_location.source.host_organization_name` | string |
| `primary_location.source.id` | string |
| `primary_location.source.is_core` | boolean |
| `primary_location.source.is_in_doaj` | boolean |
| `primary_location.source.is_oa` | boolean |
| `primary_location.source.issn` | null |
| `primary_location.source.issn_l` | null |
| `primary_location.source.type` | string |
| `primary_location.version` | string |
| `primary_topic` | object |
| `primary_topic.display_name` | string |
| `primary_topic.domain` | object |
| `primary_topic.domain.display_name` | string |
| `primary_topic.domain.id` | string |
| `primary_topic.field` | object |
| `primary_topic.field.display_name` | string |
| `primary_topic.field.id` | string |
| `primary_topic.id` | string |
| `primary_topic.score` | number |
| `primary_topic.subfield` | object |
| `primary_topic.subfield.display_name` | string |
| `primary_topic.subfield.id` | string |
| `publication_date` | string |
| `publication_year` | integer |
| `referenced_works` | array |
| `referenced_works_count` | integer |
| `related_works` | array |
| `relevance_score` | number |
| `sustainable_development_goals` | array |
| `sustainable_development_goals[].display_name` | string |
| `sustainable_development_goals[].id` | string |
| `sustainable_development_goals[].score` | number |
| `title` | string |
| `topics` | array |
| `topics[].display_name` | string |
| `topics[].domain` | object |
| `topics[].domain.display_name` | string |
| `topics[].domain.id` | string |
| `topics[].field` | object |
| `topics[].field.display_name` | string |
| `topics[].field.id` | string |
| `topics[].id` | string |
| `topics[].score` | number |
| `topics[].subfield` | object |
| `topics[].subfield.display_name` | string |
| `topics[].subfield.id` | string |
| `type` | string |
| `updated_date` | string |

---

### mol_raw.openfda_faers (86 fields)

| Field Path | Type |
|------------|------|
| `companynumb` | string |
| `duplicate` | string |
| `fulfillexpeditecriteria` | string |
| `occurcountry` | string |
| `patient` | object |
| `patient.drug` | array |
| `patient.drug[].actiondrug` | string |
| `patient.drug[].activesubstance` | object |
| `patient.drug[].activesubstance.activesubstancename` | string |
| `patient.drug[].drugadditional` | string |
| `patient.drug[].drugadministrationroute` | string |
| `patient.drug[].drugauthorizationnumb` | string |
| `patient.drug[].drugbatchnumb` | string |
| `patient.drug[].drugcharacterization` | string |
| `patient.drug[].drugcumulativedosagenumb` | string |
| `patient.drug[].drugcumulativedosageunit` | string |
| `patient.drug[].drugdosageform` | string |
| `patient.drug[].drugdosagetext` | string |
| `patient.drug[].drugenddate` | string |
| `patient.drug[].drugenddateformat` | string |
| `patient.drug[].drugindication` | string |
| `patient.drug[].drugintervaldosagedefinition` | string |
| `patient.drug[].drugintervaldosageunitnumb` | string |
| `patient.drug[].drugrecurreadministration` | string |
| `patient.drug[].drugseparatedosagenumb` | string |
| `patient.drug[].drugstartdate` | string |
| `patient.drug[].drugstartdateformat` | string |
| `patient.drug[].drugstructuredosagenumb` | string |
| `patient.drug[].drugstructuredosageunit` | string |
| `patient.drug[].medicinalproduct` | string |
| `patient.drug[].openfda` | object |
| `patient.drug[].openfda.application_number` | array |
| `patient.drug[].openfda.brand_name` | array |
| `patient.drug[].openfda.generic_name` | array |
| `patient.drug[].openfda.manufacturer_name` | array |
| `patient.drug[].openfda.nui` | array |
| `patient.drug[].openfda.package_ndc` | array |
| `patient.drug[].openfda.pharm_class_cs` | array |
| `patient.drug[].openfda.pharm_class_epc` | array |
| `patient.drug[].openfda.pharm_class_moa` | array |
| `patient.drug[].openfda.pharm_class_pe` | array |
| `patient.drug[].openfda.product_ndc` | array |
| `patient.drug[].openfda.product_type` | array |
| `patient.drug[].openfda.route` | array |
| `patient.drug[].openfda.rxcui` | array |
| `patient.drug[].openfda.spl_id` | array |
| `patient.drug[].openfda.spl_set_id` | array |
| `patient.drug[].openfda.substance_name` | array |
| `patient.drug[].openfda.unii` | array |
| `patient.patientagegroup` | string |
| `patient.patientonsetage` | string |
| `patient.patientonsetageunit` | string |
| `patient.patientsex` | string |
| `patient.patientweight` | string |
| `patient.reaction` | array |
| `patient.reaction[].reactionmeddrapt` | string |
| `patient.reaction[].reactionmeddraversionpt` | string |
| `patient.reaction[].reactionoutcome` | string |
| `patient.summary` | object |
| `patient.summary.narrativeincludeclinical` | string |
| `primarysource` | object |
| `primarysource.qualification` | string |
| `primarysource.reportercountry` | string |
| `primarysourcecountry` | string |
| `receiptdate` | string |
| `receiptdateformat` | string |
| `receivedate` | string |
| `receivedateformat` | string |
| `receiver` | object |
| `receiver.receiverorganization` | string |
| `receiver.receivertype` | string |
| `reportduplicate` | object |
| `reportduplicate.duplicatenumb` | string |
| `reportduplicate.duplicatesource` | string |
| `reporttype` | string |
| `safetyreportid` | string |
| `safetyreportversion` | string |
| `sender` | object |
| `sender.senderorganization` | string |
| `sender.sendertype` | string |
| `serious` | string |
| `seriousnessdeath` | string |
| `seriousnesshospitalization` | string |
| `seriousnessother` | string |
| `transmissiondate` | string |
| `transmissiondateformat` | string |

---

### mol_raw.openfda_labels (64 fields)

| Field Path | Type |
|------------|------|
| `adverse_reactions` | array |
| `adverse_reactions_table` | array |
| `animal_pharmacology_and_or_toxicology` | array |
| `boxed_warning` | array |
| `carcinogenesis_and_mutagenesis_and_impairment_of_fertility` | array |
| `clinical_pharmacology` | array |
| `clinical_pharmacology_table` | array |
| `clinical_studies` | array |
| `clinical_studies_table` | array |
| `contraindications` | array |
| `description` | array |
| `dosage_and_administration` | array |
| `dosage_and_administration_table` | array |
| `dosage_forms_and_strengths` | array |
| `drug_interactions` | array |
| `effective_time` | string |
| `geriatric_use` | array |
| `how_supplied` | array |
| `how_supplied_table` | array |
| `id` | string |
| `indications_and_usage` | array |
| `information_for_patients` | array |
| `mechanism_of_action` | array |
| `nonclinical_toxicology` | array |
| `openfda` | object |
| `openfda.application_number` | array |
| `openfda.brand_name` | array |
| `openfda.generic_name` | array |
| `openfda.is_original_packager` | array |
| `openfda.manufacturer_name` | array |
| `openfda.nui` | array |
| `openfda.package_ndc` | array |
| `openfda.pharm_class_cs` | array |
| `openfda.pharm_class_epc` | array |
| `openfda.pharm_class_moa` | array |
| `openfda.product_ndc` | array |
| `openfda.product_type` | array |
| `openfda.route` | array |
| `openfda.rxcui` | array |
| `openfda.spl_id` | array |
| `openfda.spl_set_id` | array |
| `openfda.substance_name` | array |
| `openfda.unii` | array |
| `overdosage` | array |
| `package_label_principal_display_panel` | array |
| `pediatric_use` | array |
| `pharmacodynamics` | array |
| `pharmacokinetics` | array |
| `pharmacokinetics_table` | array |
| `pregnancy` | array |
| `recent_major_changes` | array |
| `recent_major_changes_table` | array |
| `references` | array |
| `set_id` | string |
| `spl_medguide` | array |
| `spl_medguide_table` | array |
| `spl_product_data_elements` | array |
| `spl_unclassified_section` | array |
| `storage_and_handling` | array |
| `storage_and_handling_table` | array |
| `use_in_specific_populations` | array |
| `version` | string |
| `warnings_and_cautions` | array |
| `warnings_and_cautions_table` | array |

---

### mol_raw.pubchem (50 fields)

| Field Path | Type |
|------------|------|
| `PC_Compounds` | array |
| `PC_Compounds[].atoms` | object |
| `PC_Compounds[].atoms.aid` | array |
| `PC_Compounds[].atoms.element` | array |
| `PC_Compounds[].bonds` | object |
| `PC_Compounds[].bonds.aid1` | array |
| `PC_Compounds[].bonds.aid2` | array |
| `PC_Compounds[].bonds.order` | array |
| `PC_Compounds[].charge` | integer |
| `PC_Compounds[].coords` | array |
| `PC_Compounds[].coords[].aid` | array |
| `PC_Compounds[].coords[].conformers` | array |
| `PC_Compounds[].coords[].conformers[].style` | object |
| `PC_Compounds[].coords[].conformers[].style.aid1` | array |
| `PC_Compounds[].coords[].conformers[].style.aid2` | array |
| `PC_Compounds[].coords[].conformers[].style.annotation` | array |
| `PC_Compounds[].coords[].conformers[].x` | array |
| `PC_Compounds[].coords[].conformers[].y` | array |
| `PC_Compounds[].coords[].type` | array |
| `PC_Compounds[].count` | object |
| `PC_Compounds[].count.atom_chiral` | integer |
| `PC_Compounds[].count.atom_chiral_def` | integer |
| `PC_Compounds[].count.atom_chiral_undef` | integer |
| `PC_Compounds[].count.bond_chiral` | integer |
| `PC_Compounds[].count.bond_chiral_def` | integer |
| `PC_Compounds[].count.bond_chiral_undef` | integer |
| `PC_Compounds[].count.covalent_unit` | integer |
| `PC_Compounds[].count.heavy_atom` | integer |
| `PC_Compounds[].count.isotope_atom` | integer |
| `PC_Compounds[].count.tautomers` | integer |
| `PC_Compounds[].id` | object |
| `PC_Compounds[].id.id` | object |
| `PC_Compounds[].id.id.cid` | integer |
| `PC_Compounds[].props` | array |
| `PC_Compounds[].props[].urn` | object |
| `PC_Compounds[].props[].urn.datatype` | integer |
| `PC_Compounds[].props[].urn.label` | string |
| `PC_Compounds[].props[].urn.name` | string |
| `PC_Compounds[].props[].urn.release` | string |
| `PC_Compounds[].props[].value` | object |
| `PC_Compounds[].props[].value.ival` | integer |
| `PC_Compounds[].stereo` | array |
| `PC_Compounds[].stereo[].tetrahedral` | object |
| `PC_Compounds[].stereo[].tetrahedral.above` | integer |
| `PC_Compounds[].stereo[].tetrahedral.below` | integer |
| `PC_Compounds[].stereo[].tetrahedral.bottom` | integer |
| `PC_Compounds[].stereo[].tetrahedral.center` | integer |
| `PC_Compounds[].stereo[].tetrahedral.parity` | integer |
| `PC_Compounds[].stereo[].tetrahedral.top` | integer |
| `PC_Compounds[].stereo[].tetrahedral.type` | integer |

---

### mol_raw.reactome (18 fields)

| Field Path | Type |
|------------|------|
| `entries` | array |
| `entriesCount` | integer |
| `entries[].compartmentAccession` | array |
| `entries[].compartmentNames` | array |
| `entries[].dbId` | string |
| `entries[].disease` | boolean |
| `entries[].exactType` | string |
| `entries[].hasEHLD` | boolean |
| `entries[].hasReferenceEntity` | boolean |
| `entries[].id` | string |
| `entries[].isDisease` | boolean |
| `entries[].name` | string |
| `entries[].species` | array |
| `entries[].stId` | string |
| `entries[].summation` | text(long) |
| `entries[].type` | string |
| `rowCount` | integer |
| `typeName` | string |

---

### mol_raw.uniprot (145 fields)

| Field Path | Type |
|------------|------|
| `annotationScore` | number |
| `comments` | array |
| `comments[].commentType` | string |
| `comments[].texts` | array |
| `comments[].texts[].evidences` | array |
| `comments[].texts[].evidences[].evidenceCode` | string |
| `comments[].texts[].evidences[].id` | string |
| `comments[].texts[].evidences[].source` | string |
| `comments[].texts[].value` | text(long) |
| `entryAudit` | object |
| `entryAudit.entryVersion` | integer |
| `entryAudit.firstPublicDate` | string |
| `entryAudit.lastAnnotationUpdateDate` | string |
| `entryAudit.lastSequenceUpdateDate` | string |
| `entryAudit.sequenceVersion` | integer |
| `entryType` | string |
| `extraAttributes` | object |
| `extraAttributes.countByCommentType` | object |
| `extraAttributes.countByCommentType.ACTIVITY REGULATION` | integer |
| `extraAttributes.countByCommentType.ALTERNATIVE PRODUCTS` | integer |
| `extraAttributes.countByCommentType.BIOPHYSICOCHEMICAL PROPERTIES` | integer |
| `extraAttributes.countByCommentType.CATALYTIC ACTIVITY` | integer |
| `extraAttributes.countByCommentType.COFACTOR` | integer |
| `extraAttributes.countByCommentType.DISEASE` | integer |
| `extraAttributes.countByCommentType.FUNCTION` | integer |
| `extraAttributes.countByCommentType.INDUCTION` | integer |
| `extraAttributes.countByCommentType.INTERACTION` | integer |
| `extraAttributes.countByCommentType.MISCELLANEOUS` | integer |
| `extraAttributes.countByCommentType.PTM` | integer |
| `extraAttributes.countByCommentType.SEQUENCE CAUTION` | integer |
| `extraAttributes.countByCommentType.SIMILARITY` | integer |
| `extraAttributes.countByCommentType.SUBCELLULAR LOCATION` | integer |
| `extraAttributes.countByCommentType.SUBUNIT` | integer |
| `extraAttributes.countByCommentType.TISSUE SPECIFICITY` | integer |
| `extraAttributes.countByCommentType.WEB RESOURCE` | integer |
| `extraAttributes.countByFeatureType` | object |
| `extraAttributes.countByFeatureType.Active site` | integer |
| `extraAttributes.countByFeatureType.Alternative sequence` | integer |
| `extraAttributes.countByFeatureType.Beta strand` | integer |
| `extraAttributes.countByFeatureType.Binding site` | integer |
| `extraAttributes.countByFeatureType.Chain` | integer |
| `extraAttributes.countByFeatureType.Compositional bias` | integer |
| `extraAttributes.countByFeatureType.Disulfide bond` | integer |
| `extraAttributes.countByFeatureType.Domain` | integer |
| `extraAttributes.countByFeatureType.Glycosylation` | integer |
| `extraAttributes.countByFeatureType.Helix` | integer |
| `extraAttributes.countByFeatureType.Lipidation` | integer |
| `extraAttributes.countByFeatureType.Modified residue` | integer |
| `extraAttributes.countByFeatureType.Motif` | integer |
| `extraAttributes.countByFeatureType.Mutagenesis` | integer |
| `extraAttributes.countByFeatureType.Natural variant` | integer |
| `extraAttributes.countByFeatureType.Region` | integer |
| `extraAttributes.countByFeatureType.Sequence conflict` | integer |
| `extraAttributes.countByFeatureType.Signal` | integer |
| `extraAttributes.countByFeatureType.Site` | integer |
| `extraAttributes.countByFeatureType.Topological domain` | integer |
| `extraAttributes.countByFeatureType.Transmembrane` | integer |
| `extraAttributes.countByFeatureType.Turn` | integer |
| `extraAttributes.uniParcId` | string |
| `features` | array |
| `features[].description` | string |
| `features[].evidences` | array |
| `features[].evidences[].evidenceCode` | string |
| `features[].featureId` | string |
| `features[].location` | object |
| `features[].location.end` | object |
| `features[].location.end.modifier` | string |
| `features[].location.end.value` | integer |
| `features[].location.start` | object |
| `features[].location.start.modifier` | string |
| `features[].location.start.value` | integer |
| `features[].type` | string |
| `genes` | array |
| `genes[].geneName` | object |
| `genes[].geneName.value` | string |
| `genes[].synonyms` | array |
| `genes[].synonyms[].value` | string |
| `keywords` | array |
| `keywords[].category` | string |
| `keywords[].id` | string |
| `keywords[].name` | string |
| `organism` | object |
| `organism.commonName` | string |
| `organism.lineage` | array |
| `organism.scientificName` | string |
| `organism.taxonId` | integer |
| `primaryAccession` | string |
| `proteinDescription` | object |
| `proteinDescription.alternativeNames` | array |
| `proteinDescription.alternativeNames[].fullName` | object |
| `proteinDescription.alternativeNames[].fullName.value` | string |
| `proteinDescription.alternativeNames[].shortNames` | array |
| `proteinDescription.alternativeNames[].shortNames[].value` | string |
| `proteinDescription.cdAntigenNames` | array |
| `proteinDescription.cdAntigenNames[].value` | string |
| `proteinDescription.flag` | string |
| `proteinDescription.recommendedName` | object |
| `proteinDescription.recommendedName.ecNumbers` | array |
| `proteinDescription.recommendedName.ecNumbers[].evidences` | array |
| `proteinDescription.recommendedName.ecNumbers[].evidences[].evidenceCode` | string |
| `proteinDescription.recommendedName.ecNumbers[].evidences[].id` | string |
| `proteinDescription.recommendedName.ecNumbers[].evidences[].source` | string |
| `proteinDescription.recommendedName.ecNumbers[].value` | string |
| `proteinDescription.recommendedName.fullName` | object |
| `proteinDescription.recommendedName.fullName.value` | string |
| `proteinDescription.recommendedName.shortNames` | array |
| `proteinDescription.recommendedName.shortNames[].value` | string |
| `proteinExistence` | string |
| `references` | array |
| `references[].citation` | object |
| `references[].citation.authors` | array |
| `references[].citation.citationCrossReferences` | array |
| `references[].citation.citationCrossReferences[].database` | string |
| `references[].citation.citationCrossReferences[].id` | string |
| `references[].citation.citationType` | string |
| `references[].citation.firstPage` | string |
| `references[].citation.id` | string |
| `references[].citation.journal` | string |
| `references[].citation.lastPage` | string |
| `references[].citation.publicationDate` | string |
| `references[].citation.title` | string |
| `references[].citation.volume` | string |
| `references[].referenceComments` | array |
| `references[].referenceComments[].type` | string |
| `references[].referenceComments[].value` | string |
| `references[].referenceNumber` | integer |
| `references[].referencePositions` | array |
| `results` | array |
| `secondaryAccessions` | array |
| `sequence` | object |
| `sequence.crc64` | string |
| `sequence.length` | integer |
| `sequence.md5` | string |
| `sequence.molWeight` | integer |
| `sequence.value` | text(long) |
| `suggestions` | array |
| `suggestions[].hits` | integer |
| `suggestions[].query` | string |
| `uniProtKBCrossReferences` | array |
| `uniProtKBCrossReferences[].database` | string |
| `uniProtKBCrossReferences[].id` | string |
| `uniProtKBCrossReferences[].properties` | array |
| `uniProtKBCrossReferences[].properties[].key` | string |
| `uniProtKBCrossReferences[].properties[].value` | string |
| `uniProtkbId` | string |

---

## Part 4: Custom-Column Tables (Not JSONB)

These tables store data in typed columns, not response_body JSONB.

### mol_raw.ema_regulatory (9 columns)

| Column | Type |
|--------|------|
| `document_id` | varchar |
| `document_type` | varchar |
| `product_name` | varchar |
| `active_substance` | varchar |
| `therapeutic_area` | varchar |
| `decision_date` | date |
| `decision_type` | varchar |
| `document_url` | text |
| `summary` | text |

---

### mol_raw.journal_rss (9 columns)

| Column | Type |
|--------|------|
| `article_id` | varchar |
| `feed_source` | varchar |
| `title` | text |
| `authors` | text |
| `abstract` | text |
| `publication_date` | date |
| `link` | text |
| `doi` | varchar |
| `categories` | text[] |

---

### mol_raw.medical_news (8 columns)

| Column | Type |
|--------|------|
| `article_id` | varchar |
| `source_name` | varchar |
| `title` | text |
| `summary` | text |
| `publication_date` | date |
| `url` | text |
| `drug_mentions` | text[] |
| `therapeutic_areas` | text[] |

---

### mol_raw.openalex_ci (10 columns)

| Column | Type |
|--------|------|
| `work_id` | varchar |
| `doi` | varchar |
| `title` | text |
| `abstract` | text |
| `publication_date` | date |
| `cited_by_count` | integer |
| `concepts` | jsonb |
| `authorships` | jsonb |
| `primary_location` | jsonb |
| `open_access` | jsonb |

---

### mol_raw.orcid (10 columns)

| Column | Type |
|--------|------|
| `orcid_id` | varchar |
| `given_names` | varchar |
| `family_name` | varchar |
| `credit_name` | varchar |
| `biography` | text |
| `keywords` | jsonb |
| `current_affiliations` | jsonb |
| `works_count` | integer |
| `external_ids` | jsonb |
| `raw_response` | jsonb |

---

### mol_raw.pubmed (10 columns)

| Column | Type |
|--------|------|
| `pmid` | varchar |
| `title` | text |
| `abstract` | text |
| `authors` | jsonb |
| `journal` | varchar |
| `publication_date` | date |
| `mesh_terms` | text[] |
| `doi` | varchar |
| `publication_types` | text[] |
| `keywords` | text[] |

---

