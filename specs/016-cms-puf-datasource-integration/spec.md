# Feature Specification: CMS PUF Data Source Integration

**Feature Branch**: `016-cms-puf-datasource-integration`
**Created**: 2026-03-01
**Revised**: 2026-03-11 (canon audit rewrite)
**Status**: Draft
**Canon compliance**: Verified against dk-canon CANON.md v2026-03-11

---

## 1. Overview

Integrate ~54 free CMS/FDA/NLM/BLS/SEC public-use files into the dk-data-FE data platform, replacing $232K–$818K/yr in vendor data costs. Data flows through the existing medallion pipeline (raw → bronze → silver → gold) and is exposed exclusively via **PostgREST** for downstream consumption.

### Scope — dk-data-FE Only

| In scope | Out of scope |
|----------|-------------|
| Fetchers for 54 new data sources | MCP tools (removed — see §9) |
| SQLMesh models (bronze/silver/gold) | Upstream consumer changes |
| 6 LLM agents for Silver+ enrichment | Frontend UI changes |
| PostgREST gold-layer views | |
| K8s CronJobs for scheduled ingestion | |
| Database migrations | |

### Downstream Products

| Product | Consumes via |
|---------|-------------|
| HCP Compass | PostgREST gold views |
| HCO Navigator | PostgREST gold views |
| Lumina | PostgREST gold views |
| SageAI | PostgREST gold views |

---

## 2. User Stories

### US-1: Provider Intelligence

> As a commercial strategist, I can look up any US healthcare provider by NPI and see their prescribing patterns, procedure volumes, open payments, and network affiliations — sourced from CMS public files.

**Sources**: NPPES, Part D Prescriber, Physician/Supplier PUF, Open Payments, Care Compare

### US-2: Facility Intelligence

> As a field team manager, I can look up any US healthcare facility by CCN and see its service lines, quality ratings, cost structure, staffing patterns, and system affiliations.

**Sources**: POS, PECOS, CHOW, Hospital General Info, Inpatient/Outpatient PUFs, Hospital Quality, HCRIS, Magnet Recognition

### US-3: Drug Market Intelligence

> As a market access analyst, I can query drug-level market data including Medicare spending, formulary coverage, therapeutic classification, and competitive positioning.

**Sources**: NDC Directory, Part D/B Spending, Medicare Formulary, RBCS, USP Drug Classification

### US-4: Geographic & Population Analytics

> As a strategy lead, I can analyze geographic patterns in chronic disease prevalence, post-acute care utilization, and provider density.

**Sources**: Geographic Variation PUF, Chronic Conditions, Post-Acute Care, DMEPOS

---

## 3. Architecture

### 3.1 Medallion Pipeline

All 54 sources follow the existing dk-data-FE medallion pattern. No new schemas — data flows into the existing `raw`, `bronze`, `silver`, `gold` schemas with `cms_` table prefixes.

```
External APIs / CSV / Bulk Files
    ↓
Fetchers (BaseFetcher subclasses)
    ↓
raw.cms_* tables (Pydantic-validated loaders)
    ↓
SQLMesh bronze models (type casting, normalization)
    ↓
SQLMesh silver models (joins, dedup, entity linking)
    ↓
Silver+ enrichment (6 agents via K8s Jobs)
    ↓
SQLMesh gold models (aggregation, analytics views)
    ↓
PostgREST API (gold schema exposure)
    ↓
Downstream consumers (HTTP)
```

### 3.2 Schema Placement

All new data uses **existing** medallion schemas — no schema proliferation:

| Layer | Schema | Table prefix | Example |
|-------|--------|-------------|---------|
| Raw | `raw` | `cms_` | `raw.cms_nppes`, `raw.cms_part_d_prescriber` |
| Bronze | `bronze` | `cms_` | `bronze.cms_nppes`, `bronze.cms_part_d_prescriber` |
| Silver | `silver` | `cms_` | `silver.cms_provider_profile`, `silver.cms_facility_profile` |
| Gold | `gold` | `cms_` | `gold.cms_provider_360`, `gold.cms_facility_360` |
| Meta | `meta` | — | `meta.agent_execution_log`, `meta.agent_quarantine` |

### 3.3 Async Processing — Kubernetes Jobs

dk-data-FE is Python-only. All async processing uses **Kubernetes Jobs** — not BullMQ (Node.js-only).

| Concern | Mechanism |
|---------|-----------|
| Scheduled ingestion | K8s CronJobs (existing pattern in `k8s/base/ingestion/`) |
| Agent enrichment | K8s Jobs triggered by FastAPI job-trigger service |
| Retry on failure | K8s `backoffLimit: 3` + `restartPolicy: OnFailure` |
| Monitoring | `meta.agent_execution_log` + OpenTelemetry |

CronJob template:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cronjob-fetch-cms-nppes
spec:
  schedule: "0 3 * * 0"  # Weekly Sunday 3 AM UTC
  jobTemplate:
    spec:
      backoffLimit: 3
      template:
        spec:
          containers:
            - name: fetch
              image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:<branch>-<sha>
              command: ["python", "-m", "dk_data.ingestion.main", "cms_nppes"]
              envFrom:
                - secretRef:
                    name: doppler-dk-data-fe
          restartPolicy: OnFailure
```

### 3.4 LLM Routing — LiteLLM

All LLM calls route through the shared LiteLLM proxy using the OpenAI-compatible Python client. Direct Anthropic SDK usage is forbidden per dk-canon.

```python
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["LITELLM_BASE_URL"],  # Doppler-managed
    api_key=os.environ["LITELLM_API_KEY"],     # Doppler-managed
)

response = client.chat.completions.create(
    model="haiku",  # LiteLLM alias — not a provider model ID
    messages=[...],
    response_format={"type": "json_object"},
    temperature=0.1,
)
```

**Budget**: $175–385/month for Haiku via LiteLLM aliases.

**RPM impact**: 6 agents × ~10 calls/run × monthly = negligible. No special rate limiting needed.

### 3.5 PostgREST Gold API

5 gold views exposed via PostgREST:

| View | Key columns | Access roles |
|------|------------|-------------|
| `gold.cms_provider_profile` | `npi`, prescribing, procedures, payments, network | `analyst`, `api_user` |
| `gold.cms_facility_profile` | `ccn`, service lines, quality, cost, staffing | `analyst`, `api_user` |
| `gold.cms_drug_market_profile` | `ndc`, spending, formulary, classification | `analyst`, `api_user` |
| `gold.cms_market_analytics` | `state`, `county`, chronic conditions, utilization | `analyst`, `api_user` |
| `gold.cms_provider_network` | `source_npi`, `target_npi`, relationship, strength | `analyst`, `api_user` |

PostgREST `db-schemas` config must include `gold`:

```
PGRST_DB_SCHEMAS: "api,gold,silver,bronze,mol_api,mol_gold,mol_silver,xenon,meta"
```

---

## 4. Data Sources — 54 Files by Phase

### Phase 3: Provider MVP (7 sources)

| Source | Format | Size | Frequency | Raw Table |
|--------|--------|------|-----------|-----------|
| NPPES (NPI Registry) | CSV bulk | 8 GB | Weekly | `raw.cms_nppes` |
| Part D Prescriber | CSV | 2.5 GB | Annual | `raw.cms_part_d_prescriber` |
| Physician/Supplier PUF | CSV | 1.8 GB | Annual | `raw.cms_physician_puf` |
| Open Payments (General) | CSV | 4 GB | Annual | `raw.cms_open_payments_general` |
| Open Payments (Research) | CSV | 500 MB | Annual | `raw.cms_open_payments_research` |
| Open Payments (Ownership) | CSV | 200 MB | Annual | `raw.cms_open_payments_ownership` |
| Care Compare (Physicians) | API/CSV | 500 MB | Quarterly | `raw.cms_care_compare_physicians` |

### Phase 4: Facility MVP (10 sources)

| Source | Format | Size | Frequency | Raw Table |
|--------|--------|------|-----------|-----------|
| Provider of Services (POS) | CSV | 300 MB | Annual | `raw.cms_pos` |
| PECOS Enrollment | CSV | 200 MB | Monthly | `raw.cms_pecos` |
| Change of Ownership (CHOW) | CSV | 50 MB | Annual | `raw.cms_chow` |
| Hospital Affiliation | CSV | 100 MB | Annual | `raw.cms_hospital_affiliation` |
| Inpatient PUF (DRG) | CSV | 500 MB | Annual | `raw.cms_inpatient_puf` |
| Outpatient PUF | CSV | 300 MB | Annual | `raw.cms_outpatient_puf` |
| Hospital Quality (Star Ratings) | CSV | 50 MB | Quarterly | `raw.cms_hospital_quality` |
| Hospital General Info | CSV | 10 MB | Monthly | `raw.cms_hospital_general_info` |
| HCRIS Cost Reports | CSV | 1 GB | Annual | `raw.cms_hcris` |
| Magnet Recognition (ANCC) | Web scrape | 5 MB | Annual | `raw.cms_magnet` |

### Phase 5: Drug/Market MVP (13 sources)

| Source | Format | Size | Frequency | Raw Table |
|--------|--------|------|-----------|-----------|
| NDC Directory | API/CSV | 200 MB | Monthly | `raw.cms_ndc` |
| Part D Spending by Drug | CSV | 100 MB | Annual | `raw.cms_part_d_spending` |
| Part B Spending by Drug | CSV | 50 MB | Annual | `raw.cms_part_b_spending` |
| Medicare Formulary | CSV | 500 MB | Quarterly | `raw.cms_formulary` |
| RBCS Classification | CSV | 20 MB | Annual | `raw.cms_rbcs` |
| USP Drug Classification | CSV | 10 MB | Annual | `raw.cms_usp` |
| NUCC Taxonomy | CSV | 5 MB | Annual | `raw.cms_nucc` |
| Geographic Variation PUF | CSV | 300 MB | Annual | `raw.cms_geographic_variation` |
| Chronic Conditions PUF | CSV | 200 MB | Annual | `raw.cms_chronic_conditions` |
| Post-Acute Care PUF | CSV | 150 MB | Annual | `raw.cms_post_acute` |
| DMEPOS Utilization | CSV | 100 MB | Annual | `raw.cms_dmepos` |
| DDInter (Drug Interactions) | API | 50 MB | Monthly | `raw.cms_ddinter` |
| Stabilis (IV Compatibility) | Web | 20 MB | Quarterly | `raw.cms_stabilis` |

### Reference Tables (3)

| Table | Purpose |
|-------|---------|
| `silver.ref_drg_service_line` | DRG → service line mapping (agent-enriched) |
| `silver.ref_hcpcs_equipment` | HCPCS → equipment category mapping (agent-enriched) |
| `silver.ref_nucc_taxonomy` | NUCC code → taxonomy hierarchy |

---

## 5. Agent Pipeline — Silver+ Enrichment

6 agents handle transformations where SQL cannot reach. They call LiteLLM and write to silver tables. They run as K8s Jobs triggered monthly.

### 5.1 Base Agent

```python
class BaseAgent:
    def __init__(self):
        self.client = OpenAI(
            base_url=os.environ["LITELLM_BASE_URL"],
            api_key=os.environ["LITELLM_API_KEY"],
        )
        self.model = "haiku"  # LiteLLM alias

    async def execute(self, batch: list[dict]) -> AgentResult:
        raise NotImplementedError

    async def run(self):
        start = datetime.utcnow()
        batch = await self.load_batch()
        result = await self.execute(batch)
        await self.write_results(result.enriched)
        await self.write_quarantine(result.quarantine)
        await self.log_execution(start, result)
```

### 5.2 Agent Definitions

| # | Agent | Input | Output | Why not SQL? |
|---|-------|-------|--------|-------------|
| 1 | ServiceLineInference | `bronze.cms_inpatient_puf` DRG codes | `silver.ref_drg_service_line` | Medical domain knowledge required |
| 2 | IDNHierarchy | `bronze.cms_pecos` + `bronze.cms_chow` | `silver.cms_health_system_hierarchy` | Inference from partial ownership data |
| 3 | ReferralNetwork | `bronze.cms_physician_puf` shared patients | `silver.cms_referral_edges` | Relationship inference from co-occurrence |
| 4 | ContactVerification | `bronze.cms_nppes` phone/address | `silver.cms_verified_contacts` | Format validation + geocoding inference |
| 5 | StaffingDecomposition | `bronze.cms_hcris` cost report lines | `silver.cms_staffing_profiles` | Semi-structured cost report parsing |
| 6 | EquipmentInventoryInference | `bronze.cms_outpatient_puf` HCPCS | `silver.cms_equipment_inventory` | Equipment inference from procedure codes |

### 5.3 Validation & Quarantine

| Confidence | Action |
|-----------|--------|
| ≥ 0.8 | Auto-accept into silver |
| 0.5 – 0.79 | Accept with `needs_review` flag |
| < 0.5 | Quarantine — do not write to silver |

### 5.4 Execution Logging (Append-Only)

```sql
CREATE TABLE meta.agent_execution_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name          TEXT NOT NULL,
    agent_version       TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL,  -- RUNNING, COMPLETED, FAILED
    records_input       INTEGER,
    records_enriched    INTEGER,
    records_quarantined INTEGER,
    error_message       TEXT,
    model_used          TEXT NOT NULL,  -- LiteLLM alias
    cost_usd            NUMERIC(10,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only per dk-canon audit integrity rules
GRANT INSERT, SELECT ON meta.agent_execution_log TO api_user;
-- No UPDATE or DELETE grants
```

---

## 6. SQL Migrations

6 migrations extending the existing sequence:

| Migration | Purpose |
|-----------|---------|
| `083_cms_raw_tables.sql` | 30 `raw.cms_*` tables with standard metadata columns |
| `084_cms_bronze_seeds.sql` | SQLMesh bronze model registration (optional) |
| `085_cms_silver_tables.sql` | Silver enrichment target tables (agent outputs) |
| `086_cms_gold_views.sql` | 5 `gold.cms_*` materialized views |
| `087_cms_agent_tables.sql` | `meta.agent_execution_log`, `meta.agent_quarantine` |
| `088_cms_api_views.sql` | `api.cms_*` views + role permissions |

### Partitioning (High-Volume Tables)

```sql
-- Part D Prescriber: ~25M rows/year
CREATE TABLE raw.cms_part_d_prescriber (
    ...
) PARTITION BY RANGE (year);

-- Physician PUF: ~10M rows/year
CREATE TABLE raw.cms_physician_puf (
    ...
) PARTITION BY RANGE (year);
```

---

## 7. Infrastructure Changes

### 7.1 db-init-job.yaml

Extend (not replace) existing db-init-job:

1. **Step 9 additions**: 5 new API views for CMS gold tables
2. **Step 10 additions**: Permissions on new views for `analyst`, `api_user`
3. **Step 12 update**: Verification view count threshold ≥7 → ≥12

All additions use named dollar-quoting: `$cms$` for CMS-specific blocks.

### 7.2 PostgREST Config

Ensure `gold` is in `PGRST_DB_SCHEMAS` (configmap.yaml).

### 7.3 New CronJobs

30 new CronJob manifests in `k8s/base/ingestion/`:

| Group | Count | Schedule |
|-------|-------|----------|
| Provider | 7 | Weekly (NPPES), Annual (others) |
| Facility | 10 | Monthly–Annual |
| Drug/Market | 13 | Monthly–Annual |

All follow the existing `cronjob-fetch-*.yaml` pattern with pinned SHA tags.

### 7.4 Doppler Secrets

New entries in Doppler project `dk-data-fe`:

| Key | Purpose |
|-----|---------|
| `LITELLM_BASE_URL` | `http://litellm.infra.svc.cluster.local:8000` |
| `LITELLM_API_KEY` | LiteLLM virtual key |

No CMS API keys needed — all sources are free public-use files.

### 7.5 MCP Removal

Remove existing MCP tool routes from `src/dk_data/api/routes/mcp/` and tool definitions from `tool_registry.py` that are superseded by PostgREST gold views. See §9 for rationale.

---

## 8. Critical Integration Points

5 integration touchpoints with existing dk-data-FE code:

| ID | Change | File(s) |
|----|--------|---------|
| §A | Add `npi`, `ccn`, `params` to ingestion CLI args | `src/dk_data/ingestion/main.py` |
| §B | Generic param handling in `BaseFetcher` (not just `drug_name`) | `src/dk_data/ingestion/fetchers/base.py` |
| §C | Add `refresh_provider()`, `refresh_facility()` to `SilverGoldRefresher` | `src/dk_data/ingestion/refresh.py` |
| §D | New source registrations in source registry | `src/dk_data/ingestion/main.py` registry dict |
| §E | Schema evolution for `healthcare_facilities` PK from `(provider_id, source)` to `ccn` | Migration `085_cms_silver_tables.sql` |

---

## 9. Cold-Start Strategy — Why No MCP Tools

### Problem

When silver/gold tables are empty (fresh deployment, new source), downstream agents need data immediately.

### Previous Approach (Removed)

The original spec defined 30 MCP tools with table-read + external-API fallback. Removed because:

1. **Duplication**: behavior-labs-ai (`@repo/data-sources`) and ground-truth-charlie (adapters) already have external API clients
2. **Scope creep**: dk-data-FE is a data platform (fetch, transform, expose) — not a tool orchestrator
3. **Maintenance**: 30 tools × 2 code paths = 60 paths to maintain

### Current Approach

```
Upstream agent needs data
    ↓
Query PostgREST gold view
    ↓
Data exists? → Use it
    ↓
Empty? → Agent calls external API directly using its own client
    ↓
dk-data-FE CronJobs populate tables on schedule
    ↓
Next query hits populated PostgREST view
```

dk-data-FE stays focused: **fetch → transform → expose**. Consuming repos own their cold-start behavior.

---

## 10. Canon Compliance

| Rule | Status |
|------|--------|
| Doppler for secrets (no .env committed) | PASS |
| Image tags: `<branch>-<short-sha>` | PASS |
| db-init steps 9-12 maintained | PASS (extended) |
| PostgREST probes: `/health` | PASS (unchanged) |
| Named dollar-quoting in SQL | PASS (`$cms$`) |
| LLM via LiteLLM (no direct provider SDK) | PASS |
| Append-only audit log | PASS |
| Existing schemas (no proliferation) | PASS |
| CronJob source names match fetch code | Verified in Phase 1 |
| CI workflows preserved | PASS |

---

## 11. Verification

```bash
# Raw tables created (expect 30)
psql -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='raw' AND table_name LIKE 'cms_%';"

# Gold views created (expect 5)
psql -c "SELECT count(*) FROM information_schema.views WHERE table_schema='gold' AND table_name LIKE 'cms_%';"

# Agent log is append-only (expect false)
psql -c "SELECT has_table_privilege('api_user', 'meta.agent_execution_log', 'UPDATE');"

# PostgREST exposes gold
curl -s http://localhost:3030/gold.cms_provider_profile | jq '.[:1]'

# CronJobs deployed (expect 30)
kubectl get cronjobs -n dk-data-prod | grep cms | wc -l

# LiteLLM reachable
kubectl run test-litellm --rm -it --image=curlimages/curl -- \
  curl -s http://litellm.infra.svc.cluster.local:8000/health

# No MCP routes remain (expect 0)
grep -r 'mcp' src/dk_data/api/routes/ | grep -v '__pycache__' | wc -l

# Canon feature branch checklist
grep -r 'data-kinetic-projects' k8s/ .github/ .gitops/  # expect 0
grep -r ':latest' k8s/                                    # expect 0
```
