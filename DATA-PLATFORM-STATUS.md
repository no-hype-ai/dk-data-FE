# dk-data Platform Status — 2026-04-18

## Executive summary

The dk-data platform is **operational** across a 3-node k3s cluster with data flowing through the full medallion architecture (raw → bronze → silver → gold). **139 CronJobs** are active, **12 Grafana dashboards** are live, and the database holds **398 GB** across **709 tables**.

---

## 1. Data inventory

### 1.1 Raw layer — 69 tables with data

Source data ingested from external APIs and bulk downloads. **~58M estimated rows** across 69 populated tables.

| Table | Est. rows | Source | Cadence |
|---|---|---|---|
| hcs_raw.cms_opioid_puf | 25,508,344 | CMS Part D Opioid Prescribers | Annual |
| mol_raw.pubchem | 14,204,275 | PubChem compound data | Monthly |
| mol_raw.npi_registry | 4,100,995 | NPPES NPI Registry | Monthly |
| mol_raw.chembl | 2,868,079 | ChEMBL molecules | Monthly |
| hcs_raw.cms_ordering_providers | 2,003,091 | CMS Order & Referring | Annual |
| hcs_raw.cms_open_payments | 1,997,308 | Open Payments | Annual |
| mol_raw.openalex_ci | 1,613,038 | OpenAlex publications | Daily |
| hcs_raw.cms_physician_puf | 1,259,475 | CMS Physician PUF | Annual |
| hcs_raw.cms_mental_health_puf | 680,408 | CMS Mental Health | Annual |
| mol_raw.uniprot | 576,696 | UniProt proteins | Weekly |
| mol_raw.europepmc | 529,744 | EuropePMC literature | Weekly |
| hcs_raw.cms_outpatient_puf | 429,389 | CMS Outpatient PUF | Annual |
| mol_raw.pdb | 251,806 | PDB structures | Weekly |
| hcs_raw.hrsa_shortage_areas | 230,642 | HRSA shortage areas | Monthly |
| mol_raw.sider | 195,640 | SIDER side effects | Monthly |
| mol_raw.dailymed | 155,732 | DailyMed labels | Daily |
| mol_raw.cdc_vaccines | 141,064 | CDC vaccine data | Monthly |
| mol_raw.fda_ndc | 131,824 | FDA NDC directory | Monthly |
| hcp_raw.research_orgs_ror | 123,000 | Research Orgs ROR | Monthly |
| hcs_raw.cms_pos | 116,331 | Provider of Services | Quarterly |
| hcs_raw.cms_hospital_affiliation | 100,000 | Hospital affiliations | Quarterly |
| *+ 48 more tables* | *<100K each* | *Various CMS, FDA, WHO, IP sources* | *Various* |

### 1.2 Bronze layer — 118 tables, ~70M+ estimated rows

Typed and deduplicated data. Top tables:

| Table | Est. rows |
|---|---|
| hcs_bronze.cms_opioid_puf | 25,412,094 |
| hcs_bronze.cms_physician_puf_services | 13,550,367 |
| hcs_bronze.cms_telehealth_puf | 11,805,850 |
| hcs_bronze.cms_ordering_providers | 4,006,839 |
| hcs_bronze.cms_part_d_prescriber | 3,072,138 |
| mol_bronze.drugbank_interactions | 2,843,294 |
| hcs_bronze.cms_referring_providers | 2,003,275 |
| hcs_bronze.cms_open_payments | 1,997,000 |
| hcs_bronze.cms_physician_puf | 1,259,343 |
| hcs_bronze.cms_imaging_puf | 1,108,088 |

### 1.3 Silver layer — 96 tables, ~3M+ rows

Entity-resolved, analytics-ready tables.

| Table | Rows | Domain |
|---|---|---|
| mol_silver.physician_profiles | 1,294,299 | Molecule |
| hcs_silver.provider_profile | 1,294,128 | Healthcare |
| hcs_silver.cms_facility_profile | 116,331 | Healthcare |
| hcs_silver.cms_pos | 116,331 | Healthcare |
| hcs_silver.cms_hospital_affiliation | 99,995 | Healthcare |
| hcs_silver.cms_dmepos | 63,988 | Healthcare |
| hcs_silver.cms_rbcs | 16,618 | Healthcare |
| hcs_silver.cms_post_acute | 8,468 | Healthcare |
| hcs_silver.cms_care_compare | 5,426 | Healthcare |
| hcs_silver.cms_hospital_quality | 5,426 | Healthcare |
| ind_silver.icd11_ontology | 3,005 | Indication |
| mol_silver.icd_codes | 3,005 | Molecule |

### 1.4 Gold layer — 31 tables, ~1.3M rows

Aggregated, API-ready profiles and analytics.

| Table | Rows | Domain |
|---|---|---|
| hcs_gold.cms_provider_360 | 1,294,200 | Healthcare |
| ind_gold.indication_catalog | 3,005 | Indication |
| hcs_gold.nucc_taxonomy | 874 | Healthcare |

### 1.5 Known gaps

| Issue | Impact | Status |
|---|---|---|
| mol_bronze.chembl_molecules = 0 | Molecule silver/gold tables empty | DELETE ran during transform; re-INSERT needed on next cycle |
| FAERS events (mol_bronze) | Safety signal tables empty | statement_timeout during MERGE; needs higher timeout |
| PubChem bronze | Not yet promoted (15M raw rows) | Pending next transform cycle |
| 8 Wave B sources | 0 rows (FDA enforcement/shortages, WHO, World Bank, OECD, PBS, EMA EPAR, Health Canada) | Code committed; needs next image build to deploy |

---

## 2. SQLMesh transform pipeline

### 2.1 State

- **SQLMesh snapshots**: 238
- **SQLMesh intervals**: 668
- **Transform CronJobs**: 15 (all active, unsuspended)

### 2.2 CronJob schedules

| CronJob | Schedule | Last ran |
|---|---|---|
| mol-transform-bronze | Daily 08:00 UTC | Today |
| hcs-transform-bronze | Daily 09:30 UTC | Today |
| mol-transform-ip-bronze | Daily 08:30 UTC | Today |
| mol-transform-bronze-ext | Daily 12:30 UTC | Today |
| ind-transform | Daily 15:00 UTC | Today |
| mol-transform-silver | Daily 16:00 UTC | Apr 6 (manual catch-up today) |
| hcs-transform-silver | Daily 17:00 UTC | Apr 6 (manual catch-up today) |
| mol-transform-silver-ext | Daily 18:30 UTC | Apr 6 (manual catch-up today) |
| mol-transform-gold | Daily 21:00 UTC | Apr 6 (manual catch-up today) |
| mol-transform-gold-ext | Daily 22:00 UTC | Apr 6 (manual catch-up today) |
| cms-gold-refresh | Daily 22:30 UTC | Yesterday (failed) |
| ind-gold-transform | Daily 23:30 UTC | Yesterday |
| mart-transform | Daily 23:00 UTC | Yesterday |

### 2.3 Health issues

| Issue | Root cause | Fix |
|---|---|---|
| **WAL circuit breaker Decimal×float TypeError** | `pg_settings` returns `Decimal`, multiplied by `float` threshold | Fix committed (`1b1c7ef`); needs image rebuild |
| **WAL archiver was broken** | barman→SeaweedFS failures | Fixed by dk-alchemy (issue #704 closed) |
| **FAERS events statement_timeout** | Large MERGE exceeds default timeout | Needs `statement_timeout` increase for batch transforms |
| **cms-gold-refresh failing** | Timed out waiting for condition | Investigation needed |

---

## 3. PostgREST API

### 3.1 Status

- **Replicas**: 3 (all Running, 2/2 containers each)
- **Image**: `postgrest/postgrest:v12.2.3`
- **Authentication**: JWT-based (requires `Authorization: Bearer <token>`)
- **Default schema**: `api` (20 views)
- **Additional schema**: `mol_api` (3 views)

### 3.2 Endpoints available (via `api` schema)

| Endpoint | Source |
|---|---|
| `/molecules` | api.molecules |
| `/targets` | api.targets |
| `/patents` | api.patents |
| `/bioactivity` | api.bioactivity |
| `/competitive_landscape` | api.competitive_landscape |
| `/company_pipeline` | api.company_pipeline |
| `/molecule_properties` | api.molecule_properties |
| `/molecule_targets` | api.molecule_targets |
| `/sider_side_effects` | api.sider_side_effects |
| `/data_sources` | api.data_sources |
| `/health` | api.health |
| `/scoring` | api.scoring |
| + 8 more | |

### 3.3 Notes

- Gold tables (`hcs_gold.cms_provider_360`, etc.) are **not yet exposed** via PostgREST. They live in domain-prefixed schemas, not in `api`. Exposing them requires either adding `PGRST_DB_SCHEMAS=api,hcs_gold,mol_gold,ind_gold` to PostgREST config, or creating views in `api` that reference the gold tables.
- The `api` schema is marked **deprecated** in CLAUDE.md — new tables should use domain-prefixed schemas. PostgREST config should migrate to `PGRST_DB_SCHEMAS` multi-schema mode.

---

## 4. Infrastructure

### 4.1 Cluster

| Node | Role | Storage | Status |
|---|---|---|---|
| k3s-master-1 (penguin) | control | nvme-hdd | Ready, taint applied |
| k3s-slave-1 (krang) | general | nvme-hdd | Ready |
| k3s-slave-2 (scarecrow) | bulk | ssd-hdd | Ready |

### 4.2 Database

- **Size**: 398 GB
- **Tables**: 709
- **PVC**: 500 Gi × 2 instances on `local-path-fast` (NVMe)
- **WAL**: 1.5 GB (37.5% of 4 GB max) — healthy
- **Archiver**: healthy (last success recent, no recent failures)
- **Connections**: max_connections=200 (shared with all consumers)
- **CNPG Cluster**: `postgres-cluster` (shared — dedicated cluster planned, dk-alchemy #708)

### 4.3 Observability

- **Grafana dashboards**: 12 `dk-data-fe-*` dashboards live at `grafana.behaviorlabs.ai`
- **PrometheusRules**: 6 alert rules (disk pressure, job failure, CNPG primary, row mismatch, PgBouncer saturation, ephemeral storage)
- **WAL pressure view**: `meta.wal_pressure` — real signal (0.39%)
- **DLQ**: `meta.hydration_backlog` — operational
- **Admission control**: `meta.resource_budget` — 4 budget keys seeded

### 4.4 Automation

- **CronJobs**: 139 active, 0 suspended
- **Fetchers**: 100+ source fetchers (73 existing + 15 Wave B)
- **Transforms**: 15 SQLMesh CronJobs covering bronze/silver/gold/IP/ind/mart layers
- **Backups**: pg-backup-daily, pg-backup-weekly, pg-backup-verify (all active)

---

## 5. Remaining work

### 5.1 Immediate (next image build)

- [ ] WAL circuit breaker Decimal→float fix deploys (commit `1b1c7ef`)
- [ ] 8 Wave B sources activate (FDA, WHO, World Bank, OECD, PBS, EMA, Health Canada)
- [ ] ChEMBL bronze re-populates on next mol-transform-bronze cycle
- [ ] PubChem promotes through bronze/silver/gold

### 5.2 Near-term

- [ ] `PGRST_DB_SCHEMAS` — expose gold tables via PostgREST
- [ ] FAERS events — increase statement_timeout for batch MERGE
- [ ] cms-gold-refresh — diagnose timeout failure
- [ ] CI build pipeline — verify PR-based manifest update works (#348)
- [ ] Deploy Health Canada DPD URL fix + EMA EPAR URL fix (committed, pending image)

### 5.3 Strategic

- [ ] **Dedicated CNPG cluster for dk-data** (dk-alchemy #708) — isolate WAL, storage, connections
- [ ] Silver hub bootstrap (migrations 189-200) — canonical resolve functions
- [ ] T4 procurement — 9 licensed sources awaiting legal (#290-#298)
- [ ] Top-15 source onboarding completion (Wave B follow-ups)

---

## 6. Session delivery log

| Date | PRs | Key deliverables |
|---|---|---|
| Apr 15-16 | 9 H1 | Job hardening, alert rules, zip fix, CNPG runbook, dashboards |
| Apr 16 | 1 | feature/005 merge (27-commit prestaged hydration) |
| Apr 16 | 7 H2 | SeaweedFS, WAL pressure, DLQ, integrity, PgBouncer, audits |
| Apr 16 | 5 H3 | Dispatcher, descriptors, admission control, node taint, secrets |
| Apr 16-17 | 3 Wave A | Dashboard panels, source stubs, D.1↔D.3 integration |
| Apr 17 | 5 Wave B | 15 sources onboarded (CMS quality, FDA, intl, HCP, align) |
| Apr 17-18 | 8 fixes | db-init image, placeholder images, secret names, URLs, CI pipeline |
| **Total** | **38+** | **Full platform operational** |
