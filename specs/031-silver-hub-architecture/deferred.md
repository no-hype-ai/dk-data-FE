# Deferred Items — Silver Hub Architecture (031)

**Created**: 2026-04-11
**Status**: Tracking doc for items intentionally left out of feature 031
**Companion**: [spec.md](./spec.md)

This document tracks every data source, linkage, identifier system, and capability that was considered for the silver hub architecture rebuild and intentionally deferred to a follow-up feature. Each entry is structured the same way:

- **What's structured (free)** — what the source already gives us in v1
- **What's in prose / not ingested** — what we'd need to parse or license
- **What's lost by deferring** — the concrete capability gap
- **Why deferring is OK** — the alternative or workaround
- **v1 deliverable** — exactly what feature 031 ships for this source
- **Trigger to revisit** — the condition under which we'd build it

---

## 1. SEC EDGAR — minimal fetcher fix in 031, full bulk rebuild deferred to 032

> ⚠️ **Audit 2026-04-11 found the current SEC EDGAR fetcher is broken in multiple ways**, not just missing prose extraction. See [data-kinetic/dk-data-FE#272](https://github.com/data-kinetic/dk-data-FE/issues/272) for the full audit. After review, the cheap parts of the fix (foreign-filer coverage, ticker capture, SIC-filter correctness) were absorbed into feature 031 itself as **FR-036d** because they directly unblock `mol_silver.companies` (FR-036c). The expensive parts (XBRL bulk download, filing index replacement, filing bodies in MinIO) remain a separate follow-up feature `032-sec-edgar-bulk-rebuild`.

### What the fetcher actually does today (audited)

| Aspect | Reality |
| --- | --- |
| **API used** | EDGAR EFTS full-text search index — returns metadata only, no XBRL, no body text |
| **Filing types fetched** | `10-K`, `10-Q`, `8-K` only — **no `20-F`, `6-K`, `40-F`** so all foreign-listed pharma cos (Roche, Novartis, Sanofi, AstraZeneca, Bayer, Takeda, GSK, Daiichi Sankyo) are completely invisible |
| **SIC filter** | Half-broken — EFTS doesn't reliably return SIC, so the filter falls through to "include all" (`_is_pharma_company` returns `True` when SIC missing). In practice we store every recent filing from every company, not just pharma. |
| **What's stored in `mol_raw.sec_edgar`** | A flat-column row per filing — `accession_number`, `cik`, `company_name`, `filing_type`, `filing_date`, `document_url`, `description`. No JSONB, no XBRL, no body text, no exhibits. |
| **Bronze financial fields** | `revenue`, `net_income`, `total_assets` are **hardcoded `NULL::NUMERIC`** in `mol_bronze.sec_edgar.sql:36-41` with the comment *"genuinely unavailable from the EDGAR full-text search API"* |
| **XBRL bulk datasets** | Not ingested at all — SEC publishes ~5 GB of structured financial facts since 2009 quarterly, we download none of it |
| **Filing bodies** | `document_url` points at the filing directory but the fetcher never downloads anything from there |

### What's structured **and actually ingested** (very little)

| Field | Status |
| --- | --- |
| `cik`, `accession_number`, `filing_date`, `form_type`, `company_name`, `document_url` | ✅ Ingested |
| Ticker, SIC code, XBRL financial facts, segment financials, R&D spend | ❌ Not ingested |
| 20-F / 6-K / 40-F (foreign filings) | ❌ Not ingested |
| Exhibits (R&D narratives, clinical trial expense schedules, license agreements) | ❌ Not ingested |

### What's in prose (the original deferral category — still valid)

Drug pipeline mentions in 10-K Item 1 "Business" — drug name, research code, indication, clinical phase. Deal terms in 8-K material events — license agreements, M&A, milestones. Regulatory events in 8-K — FDA approvals, CRLs, trial readouts. Forward-looking indication mentions in 10-K Item 7 MD&A.

### Linkages we'd want

Company → drugs in pipeline. Company → company (M&A). Company → regulatory event. Company → indication area. Company → financial profile (R&D spend, revenue, segment data).

### What's lost by deferring (revised after audit)

- All foreign-listed pharma cos are entirely missing (severe gap, fixable in one line via Tier D below)
- All financial data is missing (`revenue`, `net_income`, `total_assets` hardcoded NULL)
- Pre-trial pipeline mentions (the original prose-extraction deferral)
- Deal flow / M&A intelligence
- Forward-looking indication strategy

### Why partial deferral is still OK (revised after audit)

The crude company→drug linkage that v1 of feature 031 delivers (fuzzy joins from `clinicaltrials.leadSponsor` and `fda_drugs.applicant_full_name`) **does not depend on the broken SEC EDGAR fetcher** — it works with the trial sponsor and FDA applicant names directly. So the silver hub architecture can ship without waiting for the SEC rebuild. The SEC rebuild is filed as a separate feature so it does not bloat 031's scope.

### v1 deliverable for feature 031 (silver hub architecture)

`mol_silver.companies` populated from `mol_bronze.sec_edgar` keyed on **CIK + ticker + normalized company name** (ticker now captured in 031 via FR-036d), including foreign-listed pharma cos via 20-F/6-K/40-F (also FR-036d). Fuzzy crosswalk from clinicaltrials and fda_drugs sponsor names supplies the company→drug linkage for any company that has reached a trial or an FDA application. No prose parsing. **Financial fields (revenue, R&D spend, segment data) remain hardcoded NULL until feature 032 ships the XBRL bulk fetcher.**

### Resolution path — split between feature 031 and feature 032

| Tier | What | Disk impact | Decision | Where it lands |
| --- | --- | --- | --- | --- |
| **D** | Add `20-F`, `6-K`, `40-F` to `FILING_TYPES` (~30 min) | Zero | **In scope for 031** | FR-036d in this feature's spec |
| **Ticker capture** | Per-CIK lookup via `data.sec.gov/submissions/CIK{padded}.json` with caching, persisted through raw + bronze (~1 day) | Zero | **In scope for 031** | FR-036d in this feature's spec |
| **SIC filter fix** | Use the same submissions endpoint as the source of truth instead of unreliable inline `_sic` (~half day) | Zero | **In scope for 031** | FR-036d in this feature's spec |
| **A** | Quarterly XBRL Financial Statement Data Sets bulk download (~5 GB total, ~50–100 MB/quarter) — new fetcher class, new `mol_raw.sec_xbrl_facts` table, new bronze model, new SQLMesh wiring (~1 week) | Low | **Deferred to 032** | Strongly recommended for 032 |
| **B** | Filing index bulk (`master.idx` + `company.idx`) replacing the buggy EFTS approach (~50 MB/quarter, ~1 week) | Low | **Deferred to 032** | Recommended for 032 |
| **C** | Filing bodies in MinIO partitioned by `cik/year/form_type/` (~50–100 GB pharma-only, ~2 weeks) | High | **Deferred to 032** | Conditional on confirming MinIO is not on `vmfast` ZFS pool (currently 92% full) |

### Trigger to revisit prose extraction (LLM-based)

Unchanged from original deferral: (a) a product feature requires pre-trial pipeline tracking, AND (b) commercial pipeline DB licensing (Cortellis / Adis Insight / GlobalData / BiomedTracker) is rejected on cost grounds, AND (c) feature 032 has shipped so the structured XBRL + filing-body baseline exists to extract from.


---

## 2. DailyMed / openFDA labels — indication and AE prose


| Aspect                       | Detail                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What's structured (free)** | `set_id`, `spl_id`, `openfda.brand_name`, `openfda.generic_name`, `openfda.substance_name[]`, `openfda.unii[]`, `openfda.rxcui[]`, `openfda.product_ndc[]`, `openfda.application_number[]`, `openfda.manufacturer_name`, `openfda.route[]`, `openfda.dosage_form[]`                                                                                                                                                      |
| **What's in prose**          | `indications_and_usage` (the approved use), `contraindications`, `warnings_and_precautions`, `adverse_reactions`, `drug_interactions`, `mechanism_of_action`, `pharmacokinetics`, `boxed_warning`                                                                                                                                                                                                                        |
| **Linkages we'd want**       | Drug → approved indication (MedDRA / ICD-10). Drug → contraindicated population. Drug → known AE list (MedDRA). Drug → mechanism target (UniProt). Drug → drug interaction.                                                                                                                                                                                                                                              |
| **What's lost by deferring** | Label-derived indication enrichment, label-derived AE list, label-derived MoA target linkage.                                                                                                                                                                                                                                                                                                                            |
| **Why deferring is OK**      | Drug→indication is already covered by DrugBank `<indications>`, ChEMBL `indication`, drugs@FDA approved indications, and (post-v1) ClinicalTrials.gov MeSH-mapped conditions for the trial-stage version. Drug→AE is covered by FAERS structured fields (FR-033) and SIDER. Drug→target is covered by ChEMBL targets, BindingDB, PharmGKB. The label prose is enrichment, not the only source for any of these linkages. |
| **v1 deliverable**           | `mol_silver.openfda_labels` carries forward all bronze columns including the prose fields (per FR-001 carry-forward contract) and resolves `molecule_id` / `drug_product_id` from `openfda.`* arrays. The prose fields are present in silver but not parsed for entity extraction.                                                                                                                                       |
| **Trigger to revisit**       | Consumer team requests label-derived indication/AE/MoA enrichment that the structured sources don't cover.                                                                                                                                                                                                                                                                                                               |


---

## 3. USPTO / EPO patent claims — non-FDA-approved compounds


| Aspect                       | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What's structured (free)** | `patent_number`, `application_number`, `assignees[]`, `inventors[]`, `cpc_codes[]` (Cooperative Patent Classification — pharmaceutical patents have specific A61K, C07D codes), filing/grant dates                                                                                                                                                                                                                                                                                                                 |
| **What's in prose**          | Independent and dependent claims (the legally protected scope). Description and abstract. Embodiments in the specification. IUPAC names of compounds. SMILES / InChI strings sometimes embedded. Markush structures (claim language describing a class of compounds with R-group variations).                                                                                                                                                                                                                      |
| **Linkages we'd want**       | Patent → drug (for non-FDA-approved research compounds). Patent → assignee company. Patent → therapeutic class via CPC codes.                                                                                                                                                                                                                                                                                                                                                                                      |
| **What's lost by deferring** | Linkage of research patents to specific compounds that have not yet reached FDA. Markush claim parsing (genuinely hard — requires specialized chemistry NLP).                                                                                                                                                                                                                                                                                                                                                      |
| **Why deferring is OK**      | For FDA-approved drugs, **Orange Book** is the canonical patent crosswalk (`application_number ↔ patent_number ↔ ingredient`) and is already in `mol_bronze.orange_book`. v1 attaches `molecule_id` to patents via Orange Book (FR-036a) — no parsing needed. For research patents, **PatentsView** (USPTO) and **Lens.org** publish pre-extracted compound-patent linkages for free; ingesting one of those is cheaper than building chemistry NLP. Markush parsing is a multi-month research project on its own. |
| **v1 deliverable**           | `mol_silver.patents` carries forward all bronze columns and joins `mol_bronze.orange_book` on `(application_number, patent_number)` for FDA-drug linkage. Assignees populate `mol_silver.companies` via fuzzy crosswalk. CPC codes preserved as-is.                                                                                                                                                                                                                                                                |
| **Trigger to revisit**       | Product feature needs research-patent compound tracking → ingest PatentsView or Lens.org as a new bronze source, then wire into silver.                                                                                                                                                                                                                                                                                                                                                                            |


---

## 4. SNOMED CT — clinical terminology


| Aspect                             | Detail                                                                                                                                                                                                                                                                       |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | N/A — not currently ingested                                                                                                                                                                                                                                                 |
| **What's in prose / not ingested** | Full SNOMED CT clinical terminology hierarchy: ~360K active concepts covering diseases, findings, procedures, anatomy, organisms, substances. Cross-mapped to ICD-10, ICD-11, MedDRA, and many regional code systems.                                                        |
| **Linkages we'd want**             | Condition resolution at clinical-grade granularity. SNOMED CT is the standard for EHR data and is what hospital systems use.                                                                                                                                                 |
| **What's lost by deferring**       | The richest condition crosswalk available. ICD-10/MeSH/MedDRA together cover most cases but miss SNOMED-only granularity (e.g., specific finding modifiers, anatomical sites).                                                                                               |
| **Why deferring is OK**            | SNOMED CT requires a UMLS license for redistribution. Even reading it requires UMLS access. v1 uses ICD-10 + ICD-11 + MeSH + MedDRA PT as the indication backbone, which covers the FDA, regulatory, and adverse-event use cases that dk-data consumers actually have today. |
| **v1 deliverable**                 | `mol_silver.conditions` keyed on ICD-10 / ICD-11 / MeSH / MedDRA PT. SNOMED CT not present.                                                                                                                                                                                  |
| **Trigger to revisit**             | (a) Confirm UMLS license status with the team, (b) consumer team requires EHR-compatible coding.                                                                                                                                                                             |


---

## 5. MONDO — disease ontology


| Aspect                             | Detail                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | N/A — not currently ingested                                                                                                                                                                                                                                                                                                          |
| **What's in prose / not ingested** | Monarch Disease Ontology — unified disease ontology integrating OMIM, Orphanet, DOID, ICD, MeSH, MedDRA, NCIT. Open-source. ~25K disease classes with cross-mappings.                                                                                                                                                                 |
| **Linkages we'd want**             | Rare disease resolution. Cross-mapping bridge between condition vocabularies.                                                                                                                                                                                                                                                         |
| **What's lost by deferring**       | Rare disease coverage (MONDO is much richer than ICD-10 for rare diseases). Cleaner cross-vocabulary mapping.                                                                                                                                                                                                                         |
| **Why deferring is OK**            | Open-source and free to ingest, so technically nothing blocks v1. Deferred only because it's not yet wired into any fetcher and the v1 condition hub (ICD + MeSH + MedDRA) covers ~90% of consumer queries. Adding MONDO is a follow-up of "ingest the source" + "wire into condition hub" — small enough to ship as a 2-day feature. |
| **v1 deliverable**                 | None.                                                                                                                                                                                                                                                                                                                                 |
| **Trigger to revisit**             | Rare disease indication queries become a product priority.                                                                                                                                                                                                                                                                            |


---

## 6. OMIM — Mendelian inheritance database


| Aspect                             | Detail                                                                                                                                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | N/A — not currently ingested                                                                                                                                                                                                                 |
| **What's in prose / not ingested** | Online Mendelian Inheritance in Man — gene-disease catalog with ~25K entries focused on Mendelian disorders. Phenotype + gene + inheritance pattern.                                                                                         |
| **Linkages we'd want**             | Gene → disease for Mendelian disorders. Target → indication for genetically targeted therapies.                                                                                                                                              |
| **What's lost by deferring**       | Genetics-driven target identification. Useful for rare disease drug discovery use cases.                                                                                                                                                     |
| **Why deferring is OK**            | OMIM is licensed but free for non-commercial academic use; commercial use requires a license. dk-data's licensing posture for OMIM has not been confirmed. v1 covers gene→disease via DisGeNET (already in mol_bronze) for the common cases. |
| **v1 deliverable**                 | None.                                                                                                                                                                                                                                        |
| **Trigger to revisit**             | (a) Licensing posture confirmed, (b) Mendelian disease queries become a product priority.                                                                                                                                                    |


---

## 7. JapicCTI — Japanese clinical trial registry


| Aspect                             | Detail                                                                                                                                                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What's structured (free)**       | N/A — not currently ingested                                                                                                                                                                                                                     |
| **What's in prose / not ingested** | Japan Pharmaceutical Information Center — Clinical Trials Information. Japan's WHO ICTRP-listed trial registry.                                                                                                                                  |
| **Linkages we'd want**             | Trials run in Japan that may not be cross-listed in ClinicalTrials.gov or EudraCT.                                                                                                                                                               |
| **What's lost by deferring**       | Japan-specific trial coverage.                                                                                                                                                                                                                   |
| **Why deferring is OK**            | ClinicalTrials.gov has broad international coverage (Japanese sponsors often dual-list), and EudraCT covers EU trials. Japan-only coverage is a bounded gap. Adding JapicCTI is a "build a new fetcher" project, not a hub-architecture problem. |
| **v1 deliverable**                 | None. NCT and EudraCT remain the canonical trial keys.                                                                                                                                                                                           |
| **Trigger to revisit**             | Customer with Japan-market focus requests it.                                                                                                                                                                                                    |


---

## 8. MedDRA hierarchy (HLT / HLGT / SOC)


| Aspect                             | Detail                                                                                                                                                                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | MedDRA Preferred Term (PT) and Lowest Level Term (LLT) — already in `mol_bronze.faers_events` and `sider`                                                                                                                                                     |
| **What's in prose / not ingested** | MedDRA's full hierarchy: PT → HLT (High Level Term) → HLGT (High Level Group Term) → SOC (System Organ Class). The hierarchy lets you roll up "headache", "migraine", and "tension headache" into "Headaches NEC" → "Headaches" → "Nervous system disorders". |
| **Linkages we'd want**             | Adverse event roll-up for safety signal detection. Aggregating PTs to higher-level groupings is the standard pharmacovigilance workflow.                                                                                                                      |
| **What's lost by deferring**       | AE aggregation at the HLT/HLGT/SOC level. Consumers can still query individual PTs but cannot easily roll them up to "all neurological AEs".                                                                                                                  |
| **Why deferring is OK**            | MedDRA requires a license; ICH MedDRA MSSO charges by user count. dk-data's license posture has not been confirmed. v1 uses PT and LLT for direct AE coding, which covers any single-term query.                                                              |
| **v1 deliverable**                 | `mol_silver.conditions` populated with MedDRA PT (and LLT where present). HLT / HLGT / SOC fields are NULL.                                                                                                                                                   |
| **Trigger to revisit**             | (a) MedDRA MSSO license confirmed, (b) safety signal detection becomes a product feature.                                                                                                                                                                     |


---

## 9. IMGT — antibody and immunogenetics database


| Aspect                             | Detail                                                                                                                                                                                                                                                                                               |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | `imgt_id`, antibody clone name, heavy/light chain CDR sequences (already in `mol_bronze.imgt`)                                                                                                                                                                                                       |
| **What's in prose / not ingested** | The IMGT therapeutic antibody database is partially ingested but **not yet wired into the silver molecule hub**. Sequence-hash linkage for antibodies is therefore missing.                                                                                                                          |
| **Linkages we'd want**             | Antibody therapeutic ↔ ChEMBL biologic ↔ DrugBank biotech via shared CDR sequences. Sequence-based de-duplication of antibody therapeutics across sources.                                                                                                                                           |
| **What's lost by deferring**       | Sequence-grade biologic resolution. Without it, biologics fall back to name-based matching (Pattern C) which is fuzzy.                                                                                                                                                                               |
| **Why deferring is OK**            | v1 biologic resolution priority is sequence_hash → UniProt → ChEMBL biologic → DrugBank biotech → BLA → UNII → INN → CVX → IMGT → name. The IMGT step is **listed in the priority tree** but its bootstrap procedure is deferred. Other tiers (BLA, UNII, INN with biologic stems) catch most cases. |
| **v1 deliverable**                 | `mol_silver.molecules` schema supports `sequence_hash` and `is_biologic`. The IMGT-specific bootstrap procedure that populates antibody sequence hashes is not wired in v1.                                                                                                                          |
| **Trigger to revisit**             | Antibody therapeutics become a product focus area, OR biosimilar tracking requires sequence-grade matching.                                                                                                                                                                                          |


---

## 10. Purple Book — biosimilar ↔ reference product linkage


| Aspect                             | Detail                                                                                                                                                                                                                                                                                                                            |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | `bla_number`, `product_number`, `brand_name`, `generic_name`, `reference_product_name`, `is_biosimilar`, `is_interchangeable`, `dosage_form`, `route`, `strength` (already in `mol_bronze.purple_book`)                                                                                                                           |
| **What's in prose / not ingested** | Nothing — Purple Book is fully structured. The gap is that it's **not yet wired into silver**.                                                                                                                                                                                                                                    |
| **Linkages we'd want**             | Biosimilar → reference product. Biosimilar → BLA holder. The only canonical source for FDA-licensed biosimilars.                                                                                                                                                                                                                  |
| **What's lost by deferring**       | Biosimilar tracking entirely. Today, biosimilars and their reference products are linked only by name fuzzy matching, which is unreliable.                                                                                                                                                                                        |
| **Why deferring is OK**            | **This one is actually borderline — it should probably be in v1.** Purple Book is small (~100 entries), already ingested, and the wiring is mechanical. The reason it's listed here as deferred is that the Purple Book schema audit is part of issue #253's column-retention audit and may not be complete by the time v1 ships. |
| **v1 deliverable**                 | If audit complete: Purple Book wired into `mol_silver.drug_products` with `is_biosimilar`, `is_interchangeable`, `reference_product_id`. If audit incomplete: deferred to follow-up.                                                                                                                                              |
| **Trigger to revisit**             | First v1.1 patch.                                                                                                                                                                                                                                                                                                                 |


---

## 11. DUNS / LEI / ROR — company identifiers


| Aspect                             | Detail                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | N/A — not currently ingested                                                                                                                                                                                                                                                                                               |
| **What's in prose / not ingested** | DUNS — Dun & Bradstreet's universal business identifier, ~~330M entities. LEI — Legal Entity Identifier, the regulatory standard for financial entities. ROR — Research Organization Registry, the academic-institution identifier (~~100K).                                                                               |
| **Linkages we'd want**             | Stable cross-source company identification. Today the only canonical company key dk-data has is SEC `cik`, which only covers US-listed public companies.                                                                                                                                                                   |
| **What's lost by deferring**       | Reliable company resolution for: (a) private pharma cos (no CIK), (b) non-US cos (no CIK), (c) academic sponsors of clinical trials (no CIK, but have ROR). The current `mol_silver.companies` hub is the worst-supported entity type because of this gap.                                                                 |
| **Why deferring is OK**            | DUNS requires a paid license. LEI is free but only covers financial entities (~2M, mostly banks/funds, sparse pharma coverage). ROR is free and open. v1 uses CIK + ticker + normalized name + trigram fuzzy as the company resolution path, with low confidence for unmatched names. Gold consumers filter on confidence. |
| **v1 deliverable**                 | `mol_silver.companies` keyed on (CIK, ticker, normalized_name) with trigram fuzzy fallback. Confidence often <0.95.                                                                                                                                                                                                        |
| **Trigger to revisit**             | (a) Customer with private-pharma or academic-sponsor focus, (b) DUNS license obtained or ROR ingested as a follow-up source.                                                                                                                                                                                               |


---

## 12. Provider state license numbers and DEA numbers


| Aspect                             | Detail                                                                                                                                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)**       | NPI (already in `hcs_bronze.cms_nppes`), PECOS ID, taxonomy codes                                                                                                                                                                            |
| **What's in prose / not ingested** | State medical license numbers (54 jurisdictions, no central source). DEA controlled-substance registration numbers.                                                                                                                          |
| **Linkages we'd want**             | Provider resolution against state-level data sources (state medical board records, prescription monitoring programs, malpractice databases). DEA tracking for controlled substance analytics.                                                |
| **What's lost by deferring**       | State-level provider data integration. DEA-regulated prescribing analytics.                                                                                                                                                                  |
| **Why deferring is OK**            | NPI is the federal standard and covers ~99% of provider linkage use cases. State license and DEA are sparse, jurisdiction-specific, and require per-state ingestion. PECOS ID covers Medicare-enrolled providers as a secondary federal key. |
| **v1 deliverable**                 | `hcs_silver.providers` keyed on NPI with PECOS ID secondary. State license and DEA columns reserved for future.                                                                                                                              |
| **Trigger to revisit**             | State-level analytics product feature, OR controlled-substance tracking product feature.                                                                                                                                                     |


---

## 13. Bronze stamping with `molecule_id` (Stage 4 of the linkage architecture)


| Aspect                       | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **What it is**               | Adding `molecule_id` (and other entity IDs) as a column on the heaviest bronze tables — `chembl_activities`, `bindingdb`, `pubmed`, `europepmc`, `faers_events` — and backfilling via chunked PL/pgSQL so future silver runs skip the join entirely.                                                                                                                                                                                                                                                                                       |
| **What's gained**            | ~30 second savings per silver run per stamped table.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| **What's lost by deferring** | The 30 seconds per run × number of runs per day. At our scale, this is essentially negligible.                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Why deferring is OK**      | The 2026-04-10 incident was caused by a bronze schema migration on `chembl_activities` (25M rows) that produced ~100 GB of WAL in a single transaction. **Schema migrations on million-row bronze tables are exactly the failure mode this feature exists to prevent.** v1 uses indexed joins to hubs at silver build time instead of stamping bronze; the join cost is bounded and the WAL cost is zero. The pragmatic-approach section of `silver-linkage-reference.md` is explicit that stamping is an optimization, not a requirement. |
| **v1 deliverable**           | None. Bronze schemas are not modified by feature 031.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Trigger to revisit**       | (a) Silver runs become a measurable bottleneck (current join cost <60s — not a bottleneck), (b) chunked PL/pgSQL migration patterns are battle-tested on smaller bronze tables first.                                                                                                                                                                                                                                                                                                                                                      |


---

## 14. LLM-based entity extraction (the original Story 5)


| Aspect                       | Detail                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What it is**               | Per-source CronJobs that call `litellm-server` to parse free-text fields (FAERS narratives, ClinicalTrials interventions, DailyMed indications, PubMed abstracts, patent claims, SEC 10-Ks, news headlines) and write extracted entities to side tables.                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **What's gained**            | The marginal 10-20% of entity references that the structured-field approach misses.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **What's lost by deferring** | Entity references that are genuinely prose-only and not covered by any source-API sibling field.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Why deferring is OK**      | Source-API audit during clarifications (see [spec.md Clarifications Q5](./spec.md#clarifications)) showed that ~80-90% of the cases originally assumed to need LLM extraction are already structured: openFDA harmonization arrays for FAERS and labels, ClinicalTrials.gov `derivedSection.*MeshList`, PubMed `MeshHeadingList` + `ChemicalList`, Orange Book for FDA-drug patents, static WHO INN regex for news. Cost analysis: ~$8K-30K one-time bootstrap + $2.5K-10K/year ongoing for full LLM coverage, plus model-drift management, prompt versioning, and re-extraction overhead when models upgrade. The marginal 10-20% lift does not justify those costs in v1. |
| **v1 deliverable**           | None. FR-033 through FR-036c specify the structured-field replacement.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| **Trigger to revisit**       | (a) A consumer-facing product feature requires the marginal 10-20% coverage that structured fields miss, AND (b) commercial pipeline DB licensing is rejected on cost grounds, AND (c) hub architecture is stable enough to add a new pipeline component without churn.                                                                                                                                                                                                                                                                                                                                                                                                     |


---

## 15. PubMed prose entity extraction beyond MeSH


| Aspect                       | Detail                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **What's structured (free)** | `MeshHeadingList` + `ChemicalList` (PubMed indexers tag each article with MeSH descriptors and chemical SubstanceIDs), `pmid`, `doi`, `pmcid`, `KeywordList`, `GrantList`, `DataBankList` (NCT cross-references etc.)                                                                                                                                                       |
| **What's in prose**          | Drug/target/disease mentions in title and abstract beyond what MeSH indexers caught. New compounds first reported in the article (often pre-MeSH). Specific outcome measures, statistical results, comparator arms.                                                                                                                                                         |
| **Linkages we'd want**       | Drug discovery: catching novel compounds before MeSH indexes them. Detailed comparative effectiveness extraction.                                                                                                                                                                                                                                                           |
| **What's lost by deferring** | PubMed indexers lag publication by ~6 months. New compound mentions in recent articles are missed.                                                                                                                                                                                                                                                                          |
| **Why deferring is OK**      | MeSH covers ~75% of drug/condition mentions in indexed articles (per NLM stats). For the recent-article gap, regex against `mol_bronze.who_inn` (WHO INN list of ~10K drug names) catches another ~10%. The remaining ~15% is mostly first-disclosure compounds in recent papers — useful for drug discovery scouting but not core to dk-data's current consumer use cases. |
| **v1 deliverable**           | `mol_silver.pubmed_articles` resolves drugs and conditions via `MeshHeadingList` + `ChemicalList` + WHO INN regex. Prose-mention extraction beyond that is deferred.                                                                                                                                                                                                        |
| **Trigger to revisit**       | A drug-discovery scouting product feature.                                                                                                                                                                                                                                                                                                                                  |


---

## Summary table


| #   | Item                          | Type                    | v1 ships?               | Cost to defer | Trigger                                         |
| --- | ----------------------------- | ----------------------- | ----------------------- | ------------- | ----------------------------------------------- |
| 1   | SEC EDGAR — bulk rebuild + prose | Fetcher rebuild + LLM | **Partial** — minimal fix in 031 (FR-036d: foreign filings, ticker, SIC); XBRL/index/bodies in 032; LLM prose still deferred | Medium | Issue #272 → feature 032; LLM prose gated on commercial DB rejection |
| 2   | DailyMed indication prose     | Prose parsing           | No (carry forward only) | Low           | Label-derived enrichment ask                    |
| 3   | USPTO research patents        | Chemistry NLP           | No (Orange Book only)   | Medium        | PatentsView ingestion follow-up                 |
| 4   | SNOMED CT                     | Licensed source         | No                      | Medium        | License confirmed + EHR use case                |
| 5   | MONDO                         | Open source, not wired  | No                      | Low           | Rare disease product priority                   |
| 6   | OMIM                          | Licensed for commercial | No                      | Low           | Mendelian disease product priority              |
| 7   | JapicCTI                      | New fetcher             | No                      | Low           | Japan customer                                  |
| 8   | MedDRA hierarchy              | Licensed                | No                      | Medium        | License confirmed + safety signal feature       |
| 9   | IMGT antibody bootstrap       | Wiring                  | No                      | Medium        | Antibody product focus                          |
| 10  | Purple Book wiring            | Wiring                  | **Borderline**          | Medium        | First v1.1 patch                                |
| 11  | DUNS / LEI / ROR              | New fetchers            | No                      | High          | Private/non-US/academic company tracking        |
| 12  | Provider state license / DEA  | Per-state ingestion     | No                      | Low           | State-level analytics                           |
| 13  | Bronze `molecule_id` stamping | Schema migration        | **No (intentional)**    | Negligible    | When silver join cost becomes a real bottleneck |
| 14  | LLM-based extraction          | Architecture            | **No (intentional)**    | Variable      | Marginal 10-20% becomes critical                |
| 15  | PubMed prose beyond MeSH      | NLP                     | No                      | Low           | Drug discovery scouting feature                 |


**Items that should not move to v1 even if asked**:

- #13 (bronze stamping) — this is the failure mode the feature exists to prevent
- #14 (LLM extraction) — the cost-benefit analysis is in [spec.md Clarifications](./spec.md#clarifications) and remains correct unless one of the trigger conditions changes

**Items that could quickly move to v1 if scope expands**:

- #10 (Purple Book wiring) — already in bronze, just needs the silver model
- #5 (MONDO) — open source, just needs a fetcher

