# Quickstart

## Prerequisites

All secrets are managed via Doppler (`dk-data-fe` project). The following environment variables are required:

| Variable | Purpose | Default |
|---|---|---|
| `POSTGRES_HOST` | PostgreSQL host | `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_USER` | PostgreSQL user | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password | (Doppler-managed) |
| `POSTGRES_DB` | PostgreSQL database | `dk_data` |
| `OPENFDA_API_KEY` | openFDA API key — enables limit=1000 FAERS requests | optional (unauthenticated = ~100/call) |

## Starting the Stack

```bash
# Start all services (postgres, job-trigger, postgrest)
docker compose up -d

# Rebuild job-trigger after code changes
docker compose build job-trigger && docker compose up -d --force-recreate job-trigger

# Restart PostgREST after schema changes (SQLMesh plan adds/renames views)
docker compose restart postgrest
```

Services:
- **job-trigger** (port 8000) — FastAPI ingestion API
- **postgres** (port 5433) — PostgreSQL with all mol_* / hcs_* / ind_* / hcp_* schemas
- **postgrest** (port 3030) — REST API over mol_silver, mol_gold, ind_silver, hcs_gold, hcp_gold

## Triggering Ingestion

### On-Demand (per molecule)

```bash
# Trigger FAERS ingestion for a specific molecule
curl -X POST http://localhost:8000/api/v1/data-platform/ingest \
  -H "Content-Type: application/json" \
  -d '{"source": "openfda_faers", "molecule_id": "<uuid>", "drug_name": "durvalumab"}'

# Returns {"job_id": "...", "status": "queued"}

# Poll until complete
curl http://localhost:8000/api/v1/data-platform/jobs/<job_id>

# List all available sources
curl http://localhost:8000/api/v1/data-platform/sources
```

### Scheduled (CLI)

```bash
# Run all daily sources (clinicaltrials, faers, fda labels)
python -m sync_runner --tier daily

# Run specific sources
python -m sync_runner --sources openfda_faers,clinicaltrials_gov

# Run with full refresh (ignore incremental state)
python -m sync_runner --sources chembl --full-refresh
```

## Running SQLMesh Transforms

After ingestion writes to `mol_raw.*`, run SQLMesh to propagate through bronze → silver → gold:

```bash
# Run all pending transforms
uv run sqlmesh -p src/dk_data/sqlmesh plan --auto-apply

# Run specific model
uv run sqlmesh -p src/dk_data/sqlmesh run --select mol_silver.adverse_events

# Check model state
uv run sqlmesh -p src/dk_data/sqlmesh state show
```

## Querying via PostgREST

PostgREST exposes `mol_silver`, `mol_gold`, `ind_silver`, `hcs_gold`, `hcp_gold` schemas.

```bash
# mol_silver — use Accept-Profile header
curl "http://localhost:3030/molecules?canonical_name=ilike.*durvalumab*" \
  -H "Accept-Profile: mol_silver"

curl "http://localhost:3030/adverse_events?molecule_id=eq.<uuid>&limit=100" \
  -H "Accept-Profile: mol_silver"

# mol_gold
curl "http://localhost:3030/safety_signals?molecule_id=eq.<uuid>" \
  -H "Accept-Profile: mol_gold"

curl "http://localhost:3030/market_summary?molecule_id=eq.<uuid>" \
  -H "Accept-Profile: mol_gold"

# ind_silver
curl "http://localhost:3030/epidemiology?icd10_code=eq.C34" \
  -H "Accept-Profile: ind_silver"

# hcs_gold
curl "http://localhost:3030/cms_drug_market_profile" \
  -H "Accept-Profile: hcs_gold"
```

## File-Based Sources (DrugBank, CMS USP)

These load automatically at job-trigger container startup if their target tables are empty:

```bash
# Force DrugBank reload (truncate all layers, restart triggers startup handler)
psql -h localhost -p 5433 -U postgres -d dk_data -c "
  TRUNCATE mol_raw.drugbank;
  TRUNCATE mol_bronze.drugbank;
  TRUNCATE mol_silver.drugbank;
"
docker compose restart job-trigger

# Verify DrugBank loaded (~50,000 raw rows, ~14,000 clean silver rows after transform)
curl "http://localhost:3030/drugbank?limit=5" -H "Accept-Profile: mol_silver"
```

## CMS Healthcare System Data (hcs_* schemas)

CMS provider and facility data lives in `hcs_raw.*` → `hcs_silver.*` → `hcs_gold.*`. These are separate from molecule CMS data (which goes through `mol_bronze.cms_*` → `mol_silver.drug_spending` / `mol_silver.physician_payments`).

```bash
# Fetch a CMS source
python -m dk_data.ingestion.main --source cms_nppes

# Available CMS source names (hcs_* schema):
# cms_nppes, cms_pecos, cms_physician_puf, cms_inpatient_puf,
# cms_outpatient_puf, cms_part_d_prescriber, cms_open_payments,
# cms_hcris, cms_care_compare, cms_ndc, cms_part_b_spending,
# cms_part_d_spending, cms_formulary, cms_hospital_general_info,
# cms_chow, cms_geographic_variation, cms_usp

# Refresh hcs_gold views after ingestion + transform
curl -X POST http://localhost:8000/cms/gold/refresh

# Query hcs_gold via PostgREST
curl "http://localhost:3030/cms_provider_360" -H "Accept-Profile: hcs_gold"
curl "http://localhost:3030/cms_drug_market_profile" -H "Accept-Profile: hcs_gold"
curl "http://localhost:3030/cms_facility_360" -H "Accept-Profile: hcs_gold"
```

## LLM Agents (Silver+ Enrichment)

Six LLM-powered agents handle enrichment where SQL alone cannot reach (CMS healthcare system data):

```bash
# Trigger via API
curl -X POST http://localhost:8000/api/v1/agents/service_line_inference/run
curl -X POST http://localhost:8000/api/v1/agents/idn_hierarchy/run
curl -X POST http://localhost:8000/api/v1/agents/referral_network/run
curl -X POST http://localhost:8000/api/v1/agents/contact_verification/run
curl -X POST http://localhost:8000/api/v1/agents/staffing_decomposition/run
curl -X POST http://localhost:8000/api/v1/agents/equipment_inventory_inference/run
```

Agents call LLMs via LiteLLM proxy (`LITELLM_BASE_URL` + `LITELLM_API_KEY`). Records with confidence >= 0.8 go directly to silver; 0.5–0.79 go to silver flagged `needs_review`; < 0.5 go to `meta.agent_quarantine`.

## Monitoring

```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# Layer row counts (from metrics endpoint or direct SQL)
psql -h localhost -p 5433 -U postgres -d dk_data -c "
  SELECT 'mol_silver.molecules' AS tbl, COUNT(*) FROM mol_silver.molecules
  UNION ALL
  SELECT 'mol_silver.adverse_events', COUNT(*) FROM mol_silver.adverse_events
  UNION ALL
  SELECT 'mol_gold.safety_signals', COUNT(*) FROM mol_gold.safety_signals
  UNION ALL
  SELECT 'mol_gold.market_summary', COUNT(*) FROM mol_gold.market_summary;
"
```
