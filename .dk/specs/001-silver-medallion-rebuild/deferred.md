# Deferred Items — Silver Medallion Rebuild

This document tracks every item the spec acknowledges but does NOT deliver in v1. Three sections:

1. **Known gaps in the linkage architecture** (10 items from `silver-linkage-reference.md`)
2. **Ask Nick later** (10 items from `transformation-reliability-low-tech-solutions.md` §13 — infrastructure changes that would help but are out of scope)
3. **Out-of-scope follow-ups** (items intentionally cut from this feature)

---

## Section 1 — Known gaps in the linkage architecture

### Gap 1 — Biologic structural identity

**Issue**: No canonical structural key for biologics. Sequence hash is the right answer but requires sequence data we don't have for every biologic.
**v1 mitigation**: `mol_silver.molecules` allows `inchi_key` NULL, supports `sequence_hash` and `is_biologic`, and the molecule resolve function falls back through UNII / BLA / DrugBank biotech / WHO INN with biologic stems / CVX / IMGT / name (FR-013).
**Trigger to revisit**: Antibody therapeutics become a product focus area, OR biosimilar tracking requires sequence-grade matching.

### Gap 2 — Combination drug AE attribution

**Issue**: A FAERS report for "Combivent" maps to one product but two molecules (ipratropium + albuterol). AE attribution is ambiguous — is the AE caused by either molecule, both, or the combination?
**v1 mitigation**: Always link to product first via `mol_silver.drug_products`, then expand to ingredients in gold via `mol_silver.drug_product_ingredients`. Tag AE rows with `attribution_type IN ('primary_suspect', 'concomitant', 'combo_unknown')`.
**Trigger to revisit**: Pharmacovigilance product feature requires per-ingredient AE attribution.

### Gap 3 — Salt forms

**Issue**: "atorvastatin" vs "atorvastatin calcium" — different InChIKeys, clinically equivalent for most queries.
**v1 mitigation**: `parent_molecule_id` column on `mol_silver.molecules` (FR-011). Salt forms link to their parent. Clinical queries follow the parent pointer; chemical queries use the salt-specific ID.

### Gap 4 — Stereoisomers

Same as Gap 3 — uses `parent_molecule_id`.

### Gap 5 — Companies (worst-supported entity type)

**Issue**: No canonical identifier system is fully ingested. CIK only covers US public companies. Most matches will be at the name or fuzzy tier.
**v1 mitigation**: Bootstrap with CIK + ticker + normalized name + trigram fuzzy. `mol_silver.companies` is flagged as a degraded entity type. Gold consumers MUST filter `confidence ≥ 0.95` (FR-013b).
**Trigger to revisit**: (a) Customer with private-pharma or academic-sponsor focus, (b) DUNS/LEI/ROR licensing or ingestion is resolved.

### Gap 6 — SNOMED CT licensing

**Issue**: Gold standard for clinical terminology. Requires UMLS license for redistribution. ~360K active concepts covering diseases, findings, procedures, anatomy, organisms.
**v1 mitigation**: Use ICD-10 + ICD-11 + MeSH + MedDRA PT as the indication backbone (covers FDA, regulatory, AE use cases).
**Trigger to revisit**: (a) Confirm UMLS license status with team, (b) consumer team requires EHR-compatible coding granularity.

### Gap 7 — MedDRA hierarchy

**Issue**: We have PT (Preferred Term) level only. Can't roll up to HLT/HLGT/SOC for AE analysis. The MedDRA hierarchy enables aggregating "headache", "migraine", "tension headache" into "Headaches NEC" → "Headaches" → "Nervous system disorders" — the standard pharmacovigilance workflow.
**v1 mitigation**: PT-only resolution. Consumers can query individual PTs but cannot easily roll up to "all neurological AEs".
**Trigger to revisit**: (a) MedDRA MSSO license confirmed, (b) safety signal detection becomes a product feature.

### Gap 8 — Fuzzy match quality

**Issue**: Trigram fuzzy matching (Pattern D) produces false positives. Gold-layer joins can be polluted if confidence is ignored.
**v1 mitigation**: Two-tier confidence (FR-013a/13b). Resolve functions return matches at `pg_trgm` similarity ≥ 0.85 with the computed `confidence`; matches below 0.85 return NULL. Gold-layer consumers MUST filter `confidence ≥ 0.95`.

### Gap 9 — Purple Book integration

**Issue**: Currently not wired into silver. Biosimilar ↔ reference product linkage is entirely lost. Purple Book is the only canonical source for FDA-licensed biosimilars (~100 entries, BLA + product-keyed, includes `is_biosimilar` and `reference_product_name`).
**v1 mitigation**: `mol_silver.drug_products` schema supports `is_biosimilar` and `reference_product_id` columns. The bootstrap reads existing bronze sources but Purple Book wiring is **borderline** — small (~100 rows), already in bronze, and fits in v1 IF the Purple Book column-retention audit completes pre-merge. If not, deferred to v1.1.
**Trigger to revisit**: First v1.1 patch.

### Gap 10 — IMGT antibody clones

**Issue**: Currently partially ingested but not wired into silver. Antibody clone names don't link across sources by structure.
**v1 mitigation**: Molecule hub schema supports `sequence_hash` and `is_biologic`. Other tiers (BLA, UNII, INN with biologic stems) catch most cases.
**Trigger to revisit**: Antibody therapeutics become a product focus area.

---

## Section 2 — Ask Nick later (infrastructure asks)

These are improvements that would significantly help but require dk-alchemy changes. **None of them are required for dk-data-FE to ship feature 001.** They go on a separate ask list. We don't wait for them to start fixing dk-data-FE.

### P1 — most impactful

**N1**. Set `restart_after_crash = on` in the postgres cluster spec.
- **Why**: A single barman-cloud archiver crash should not take down the primary postgres pod.
- **Where**: dk-alchemy CNPG cluster spec.
- **Who**: Nick.
- **Cost to defer**: We crash on every archiver crash (~monthly).

**N2**. Enable `pg_stat_statements` and `auto_explain` in `shared_preload_libraries`.
- **Why**: Query-level visibility. Without it, dk-data-FE has to build its own substitute (FR-041 — `meta.slow_query_log`).
- **Where**: dk-alchemy CNPG postgresql.conf.
- **Cost to defer**: We maintain a fragile application-side substitute.

**N3**. Free `vmfast` ZFS pool space and bring `k3s-slave-1` online.
- **Why**: Storage capacity is the actual disk-pressure root cause behind the 2026-04-10 incident sequence. Single-node K3s is the HA gap.
- **Where**: dk-alchemy Proxmox + K3s.
- **Cost to defer**: Any disk-related event takes the cluster down. No HA.

### P2 — would help significantly

**N4**. Increase postgres pod resources (8 CPU / 32 GiB) and tune postgresql.conf accordingly: `shared_buffers = 8 GB`, `max_wal_size = 16 GB`, `wal_compression = lz4`.
- **Why**: 4x the WAL ceiling, 16x the buffer cache, ~30% smaller WAL via compression. Lifts most of the application-side budget pressure.
- **Cost to defer**: dk-data-FE has to fit inside 4 GB WAL ceiling forever.

**N5**. Switch barman-cloud target from SeaweedFS to MinIO.
- **Why**: SeaweedFS is on the same disk as the postgres primary (single point of failure). MinIO is on a separate volume.
- **Cost to defer**: Backup and primary share fate.

**N6**. Install Prometheus Operator CRDs so dk-data-FE can deploy `ServiceMonitor` and `PrometheusRule` directly.
- **Why**: Currently every observability deployment has to use raw scrape configs.
- **Cost to defer**: More verbose alert rule deployment.

**N7**. Add an off-host backup target (S3 or another physical host).
- **Why**: All current backups are on the same Proxmox host as the primary postgres.
- **Cost to defer**: Single-host failure loses both primary and backups.

### P3 — nice-to-have

**N8**. Install `pgmq` for queue-based scheduling.
- **Why**: dk-data uses CronJobs + advisory locks for job queueing. `pgmq` would be cleaner.
- **Cost to defer**: dk-data-FE keeps the CronJob+`meta.job_locks` pattern.

**N9**. Add proper PITR via `pgbackrest` or `wal-g` (replace flaky barman-cloud).
- **Why**: barman-cloud has crashed twice this month. PITR is unreliable.
- **Cost to defer**: Recovery to a point-in-time is best-effort.

**N10**. HA postgres with replicas across two physical hosts.
- **Why**: True HA requires more than one physical host.
- **Cost to defer**: Single-host failure = full outage.

---

## Section 3 — Out-of-scope follow-ups

| # | Item | Why deferred | Trigger to revisit |
|---|---|---|---|
| 1 | LLM-based entity extraction from prose | Source-API audit found ~80–90% of cases have a structured sibling field. LLM cost ($8K–30K one-time + $2.5K–10K/year) does not justify the marginal lift | A consumer-facing product feature requires the marginal 10–20% coverage |
| 2 | DailyMed indication-prose parsing | Drug→indication is already covered by DrugBank `<indications>`, ChEMBL `indication`, drugs@FDA approved indications | Consumer team requests label-derived indication enrichment |
| 3 | Non-FDA patent claim parsing for research compounds | Orange Book covers FDA-approved drug patents in v1. Research patents need chemistry NLP or PatentsView/Lens.org ingestion | Research-patent compound tracking becomes a product priority |
| 4 | SEC EDGAR 10-K Business section pipeline mentions | Crude company→drug linkage delivered via fuzzy joins from `clinicaltrials.leadSponsor` and `fda_drugs.applicant_full_name`. Commercial pharma pipeline DBs (Cortellis, Adis Insight, BiomedTracker, GlobalData) do this professionally | Pre-trial pipeline tracking becomes a product priority |
| 5 | MONDO disease ontology ingestion | Open-source and free, just not yet wired. v1 condition hub (ICD + MeSH + MedDRA PT) covers ~90% of consumer queries | Rare disease indication queries become a product priority |
| 6 | OMIM Mendelian inheritance database | Licensing posture not confirmed | (a) Licensing confirmed, (b) Mendelian disease queries become a product priority |
| 7 | JapicCTI Japanese trial registry | Japan-only coverage gap. Adding it is a "build a new fetcher" project | Customer with Japan-market focus |
| 8 | Provider state license / DEA numbers | Sparse, jurisdiction-specific, requires per-state ingestion | State-level analytics product feature |
| 9 | Bronze stamping with `molecule_id` columns | This is exactly the failure mode this feature exists to prevent. Schema migrations on 25M+ row bronze tables produce 100+ GB WAL | When silver join cost becomes a real bottleneck (current cost ~30 s/run, not a bottleneck) |
| 10 | Tray pattern for non-bronze tables | The 5 specific bronze tables (FR-037a) cover the heaviest workloads. Other tables don't hit the WAL ceiling | A new heavy-load workload exceeds the per-CronJob WAL budget |

---

## Summary

| Section | Items | Status |
|---|---|---|
| 1. Known gaps in linkage architecture | 10 | 4 fully mitigated in v1 (3, 4, 8, partial 1+5); 6 deferred (2, 6, 7, 9, 10, full 1+5) |
| 2. Ask Nick later (infrastructure) | 10 | All 10 deferred to dk-alchemy. None are blockers for v1. |
| 3. Out-of-scope follow-ups | 10 | All explicitly cut from v1 |

**Items that should NOT move to v1 even if requested**:
- #9 (bronze stamping) — this is the failure mode the feature exists to prevent
- #1 (LLM extraction) — cost-benefit analysis is documented and remains correct unless one of the trigger conditions changes

**Items that could quickly move to v1 if scope expands**:
- Gap 9 (Purple Book wiring) — already in bronze, just needs the silver model
- #5 (MONDO) — open source, just needs a fetcher
