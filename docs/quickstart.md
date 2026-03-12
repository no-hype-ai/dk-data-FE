# Quickstart

## CMS Data Sources

### Environment Variables

All secrets are managed via Doppler (`dk-data-fe` project). The following variables are required for CMS data source ingestion and agent enrichment:

| Variable | Purpose | Default |
|----------|---------|---------|
| `LITELLM_BASE_URL` | LiteLLM proxy endpoint for agent LLM calls | `http://litellm.infra.svc.cluster.local:8000` |
| `LITELLM_API_KEY` | LiteLLM virtual key | (Doppler-managed) |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_PORT` | PostgreSQL port | `5433` |
| `POSTGRES_USER` | PostgreSQL user | `dk_data` |
| `POSTGRES_PASSWORD` | PostgreSQL password | (Doppler-managed) |
| `POSTGRES_DB` | PostgreSQL database name | `dk_data` |

No CMS API keys are needed -- all 54 sources are free public-use files.

### Running a CMS Fetcher

Fetch a single CMS data source into the `raw` schema:

```bash
python -m dk_data.ingestion.main --source cms_nppes
```

Available source names follow the `cms_*` convention (e.g., `cms_part_d_prescriber`, `cms_physician_puf`, `cms_open_payments`, `cms_care_compare`, `cms_pecos`, `cms_hcris`, `cms_ndc`, etc.). See the source registry in `src/dk_data/ingestion/main.py` for the full list.

You can also pass entity-specific parameters:

```bash
# Fetch by NPI
python -m dk_data.ingestion.main --source cms_nppes --npi 1234567890

# Fetch by CCN (facility identifier)
python -m dk_data.ingestion.main --source cms_hospital_general_info --ccn 050454
```

### Triggering an Agent

Silver+ enrichment agents can be triggered via the FastAPI job-trigger service:

```bash
# Trigger a specific agent
curl -X POST http://localhost:8000/api/v1/agents/{agent_name}/run

# Example: run the ServiceLineInference agent
curl -X POST http://localhost:8000/api/v1/agents/service_line_inference/run

# Example: run the IDNHierarchy agent
curl -X POST http://localhost:8000/api/v1/agents/idn_hierarchy/run
```

Available agents: `service_line_inference`, `idn_hierarchy`, `referral_network`, `contact_verification`, `staffing_decomposition`, `equipment_inventory_inference`.

### Refreshing Gold Views

Refresh the materialized gold views after new data has been ingested and transformed:

```bash
# Refresh all CMS gold views
curl -X POST http://localhost:8000/cms/gold/refresh

# Verify gold views via PostgREST
curl -s http://localhost:3030/cms_provider_profile | jq '.[:1]'
curl -s http://localhost:3030/cms_facility_profile | jq '.[:1]'
curl -s http://localhost:3030/cms_drug_market_profile | jq '.[:1]'
curl -s http://localhost:3030/cms_market_analytics | jq '.[:1]'
curl -s http://localhost:3030/cms_provider_network | jq '.[:1]'
```

### Full Pipeline

To run the complete CMS pipeline end-to-end:

1. Fetch raw data: `python -m dk_data.ingestion.main --source cms_nppes` (repeat per source)
2. Run SQLMesh transforms: `make sqlmesh-run`
3. Trigger agents: `POST /api/v1/agents/{agent_name}/run` (for each agent)
4. Refresh gold views: `POST /cms/gold/refresh`
5. Query via PostgREST: `GET http://localhost:3030/cms_provider_profile`

In production, steps 1-4 are automated via K8s CronJobs on monthly/quarterly/annual schedules.
