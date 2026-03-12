# Agent Pipeline -- Silver+ Enrichment

## Overview

The CMS PUF integration includes 6 LLM-powered agents that handle Silver+ enrichment -- transformations where SQL alone cannot reach. Each agent reads from bronze/silver tables, calls an LLM via LiteLLM for inference, and writes enriched results to silver target tables.

All agents inherit from `BaseAgent` (`src/dk_data/agents/base_agent.py`) and run as Kubernetes Jobs (not BullMQ, since dk-data-FE is Python-only).

## The 6 Agents

| # | Agent | Input | Output Table | Purpose |
|---|-------|-------|-------------|---------|
| 1 | **ServiceLineInference** | `bronze.cms_inpatient_puf` DRG codes | `silver.ref_drg_service_line` | Maps DRG codes to clinical service lines using medical domain knowledge |
| 2 | **IDNHierarchy** | `bronze.cms_pecos` + `bronze.cms_chow` | `silver.cms_health_system_hierarchy` | Infers integrated delivery network ownership hierarchies from partial ownership data |
| 3 | **ReferralNetwork** | `bronze.cms_physician_puf` shared patients | `silver.cms_referral_edges` | Infers provider referral relationships from patient co-occurrence patterns |
| 4 | **ContactVerification** | `bronze.cms_nppes` phone/address | `silver.cms_verified_contacts` | Validates and normalizes contact information including format validation and geocoding inference |
| 5 | **StaffingDecomposition** | `bronze.cms_hcris` cost report lines | `silver.cms_staffing_profiles` | Parses semi-structured hospital cost reports to extract staffing profiles |
| 6 | **EquipmentInventoryInference** | `bronze.cms_outpatient_puf` HCPCS codes | `silver.cms_equipment_inventory` | Infers facility equipment inventory from outpatient procedure codes |

## Architecture

```
BaseAgent (src/dk_data/agents/base_agent.py)
    |
    |-- OpenAI client (pointed at LiteLLM proxy)
    |       base_url = LITELLM_BASE_URL
    |       api_key  = LITELLM_API_KEY
    |       model    = "haiku" (LiteLLM alias)
    |
    |-- PostgreSQL connection (psycopg2)
    |       host = POSTGRES_HOST
    |       port = POSTGRES_PORT (default 5433)
    |
    |-- Execution flow:
    |       run()
    |        -> load_batch()        # Read from bronze/silver
    |        -> execute(batch)      # Call LLM, produce AgentResult
    |        -> write_results()     # Write enriched to silver
    |        -> write_quarantine()  # Write low-confidence to meta.agent_quarantine
    |        -> log_execution()     # Append to meta.agent_execution_log
```

### BaseAgent Contract

Every agent subclass must implement:

- `AGENT_NAME: str` -- unique identifier (e.g., `"service_line_inference"`)
- `AGENT_VERSION: str` -- semantic version (e.g., `"0.1.0"`)
- `load_batch() -> list[dict]` -- load input records from the database
- `execute(batch) -> AgentResult` -- process records via LLM, return enriched + quarantine lists
- `write_results(enriched) -> None` -- write accepted records to the silver target table

### LLM Integration

All LLM calls go through the LiteLLM proxy using the OpenAI-compatible Python client. Direct Anthropic SDK usage is forbidden per dk-canon.

```python
# Internal to BaseAgent.call_llm()
response = self.client.chat.completions.create(
    model="haiku",                              # LiteLLM alias
    messages=[...],
    response_format={"type": "json_object"},    # Structured output
    temperature=0.1,                            # Low temperature for determinism
)
```

Budget: $175-385/month for Haiku via LiteLLM aliases. RPM impact is negligible (6 agents x ~10 calls/run x monthly).

## Confidence Thresholds

Every record produced by an agent includes a confidence score. The disposition depends on the score:

| Confidence Score | Action | Destination |
|-----------------|--------|-------------|
| >= 0.8 | Auto-accept | Silver target table |
| 0.5 -- 0.79 | Accept with `needs_review` flag | Silver target table (flagged) |
| < 0.5 | Quarantine -- do not write to silver | `meta.agent_quarantine` |

These thresholds are defined as class constants on `BaseAgent`:

- `CONFIDENCE_THRESHOLD_ACCEPT = 0.8`
- `CONFIDENCE_THRESHOLD_REVIEW = 0.5`

## How to Trigger Agents

### 1. Kubernetes CronJob (Production -- Monthly)

Agents run on a monthly schedule via K8s CronJobs. Each agent has its own CronJob manifest in `k8s/base/ingestion/`.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cronjob-agent-service-line-inference
spec:
  schedule: "0 6 1 * *"   # 1st of month, 6 AM UTC
  jobTemplate:
    spec:
      backoffLimit: 3
      template:
        spec:
          containers:
            - name: agent
              image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:<branch>-<sha>
              command: ["python", "-m", "dk_data.agents.service_line_inference"]
              envFrom:
                - secretRef:
                    name: doppler-dk-data-fe
          restartPolicy: OnFailure
```

### 2. API Endpoint (On-Demand)

Trigger any agent via the FastAPI job-trigger service:

```bash
POST /api/v1/agents/{agent_name}/run

# Examples:
curl -X POST http://localhost:8000/api/v1/agents/service_line_inference/run
curl -X POST http://localhost:8000/api/v1/agents/idn_hierarchy/run
curl -X POST http://localhost:8000/api/v1/agents/referral_network/run
curl -X POST http://localhost:8000/api/v1/agents/contact_verification/run
curl -X POST http://localhost:8000/api/v1/agents/staffing_decomposition/run
curl -X POST http://localhost:8000/api/v1/agents/equipment_inventory_inference/run
```

### 3. Kubernetes Job Template (Ad-Hoc)

For one-off runs or debugging, create a K8s Job directly:

```bash
kubectl create job agent-sli-manual --from=cronjob/cronjob-agent-service-line-inference -n dk-data-prod
```

## Quarantine Management

Records with confidence < 0.5 are quarantined in `meta.agent_quarantine`. These records need manual review before they can be promoted to silver tables.

### Quarantine Table Schema

```sql
meta.agent_quarantine (
    id              UUID PRIMARY KEY,
    agent_name      TEXT NOT NULL,
    execution_id    UUID NOT NULL,
    record_data     JSONB NOT NULL,
    reason          TEXT,
    confidence_score NUMERIC(5,4),
    status          TEXT NOT NULL,  -- PENDING, APPROVED, REJECTED
    created_at      TIMESTAMPTZ DEFAULT now()
)
```

### Quarantine Endpoints

```bash
# List quarantined records (via PostgREST)
curl "http://localhost:3030/agent_quarantine?status=eq.PENDING"

# Filter by agent
curl "http://localhost:3030/agent_quarantine?agent_name=eq.service_line_inference&status=eq.PENDING"

# Approve a quarantined record (PATCH via PostgREST)
curl -X PATCH "http://localhost:3030/agent_quarantine?id=eq.<uuid>" \
  -H "Content-Type: application/json" \
  -d '{"status": "APPROVED"}'

# Reject a quarantined record
curl -X PATCH "http://localhost:3030/agent_quarantine?id=eq.<uuid>" \
  -H "Content-Type: application/json" \
  -d '{"status": "REJECTED"}'
```

## Cost Monitoring

Agent execution costs are tracked in `meta.agent_execution_log` (append-only per dk-canon audit rules).

### Execution Log Schema

```sql
meta.agent_execution_log (
    id                  UUID PRIMARY KEY,
    agent_name          TEXT NOT NULL,
    agent_version       TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL,  -- RUNNING, COMPLETED, FAILED
    records_input       INTEGER,
    records_enriched    INTEGER,
    records_quarantined INTEGER,
    error_message       TEXT,
    model_used          TEXT NOT NULL,  -- LiteLLM alias (e.g., "haiku")
    cost_usd            NUMERIC(10,4), -- Populated post-hoc from LiteLLM billing
    created_at          TIMESTAMPTZ DEFAULT now()
)
```

### Monitoring Queries

```bash
# Recent agent executions (via PostgREST)
curl "http://localhost:3030/agent_execution_log?order=started_at.desc&limit=20"

# Failed executions
curl "http://localhost:3030/agent_execution_log?status=eq.FAILED&order=started_at.desc"

# Cost summary by agent (via psql)
psql -c "
  SELECT agent_name,
         count(*) AS runs,
         sum(records_enriched) AS total_enriched,
         sum(records_quarantined) AS total_quarantined,
         sum(cost_usd) AS total_cost_usd
  FROM meta.agent_execution_log
  WHERE status = 'COMPLETED'
  GROUP BY agent_name
  ORDER BY total_cost_usd DESC;
"
```

The `cost_usd` column is populated post-hoc from the LiteLLM billing API, not at execution time. The execution log is append-only -- no UPDATE or DELETE grants are issued to `api_user`.
