# API Contracts: CMS PUF & Platform Data Reconciliation

**Phase**: 1 — Design
**Feature**: `019-cms-puf-platform-reconciliation`
**Date**: 2026-03-27

These contracts define the two new API routers added by this feature. All endpoints follow the existing FastAPI patterns in `src/dk_data/api/routes/`.

---

## Router 1: Data Tools Gateway

**Router prefix**: `/api/v1/data-tools`
**File**: `src/dk_data/api/routes/data_tools.py`

### GET /api/v1/data-tools/registry

Returns all registered data tools with metadata.

**Response** `200 OK`:
```json
{
  "tools": [
    {
      "tool_id": "cms_part_d_spending",
      "name": "CMS Part D Drug Spending",
      "category": "cms_bulk",
      "supported_query_keys": ["generic_name", "year"],
      "last_refresh": "2026-03-01T00:00:00Z",
      "last_refresh_status": "success",
      "requires_file": true
    }
  ],
  "total": 54
}
```

**Errors**:
- `500` — database unavailable

---

### POST /api/v1/data-tools/backfill

Trigger a fresh fetch + transform for a registered source.

**Request body**:
```json
{
  "source_name": "cms_part_d_spending",
  "force": false
}
```

- `source_name` (required): must match a key in `meta.data_sources`
- `force` (optional, default `false`): if `true`, skip local freshness check and always fetch

**Response** `202 Accepted`:
```json
{
  "job_id": "backfill-cms_part_d_spending-20260327T120000Z",
  "source_name": "cms_part_d_spending",
  "status": "queued",
  "skipped_fetch": false,
  "message": "Backfill queued. Check meta.refresh_log for completion."
}
```

**Response** `200 OK` (when local data is fresh and `force=false`):
```json
{
  "source_name": "cms_part_d_spending",
  "status": "skipped",
  "skipped_fetch": true,
  "last_refresh": "2026-03-01T00:00:00Z",
  "message": "Local data is sufficiently recent. Pass force=true to override."
}
```

**Errors**:
- `404` — `source_name` not found in registry
- `409` — backfill already running for this source
- `500` — internal error starting job

---

### GET /api/v1/data-tools/{source_name}/status

Get the current status and last refresh metadata for a single source.

**Response** `200 OK`:
```json
{
  "source_name": "cms_part_d_spending",
  "last_successful_refresh": "2026-03-01T00:00:00Z",
  "last_refresh_status": "success",
  "records_inserted_last_run": 42000,
  "requires_file": true
}
```

**Errors**:
- `404` — source not found

---

## Router 2: Agents

**Router prefix**: `/api/v1/agents`
**File**: `src/dk_data/api/routes/agents.py`

### GET /api/v1/agents

List all registered agents with their last run metadata.

**Response** `200 OK`:
```json
{
  "agents": [
    {
      "agent_id": "service_line_inference",
      "description": "Infers clinical service lines from DRG claims data",
      "schedule": "monthly",
      "last_run": "2026-03-01T00:00:00Z",
      "last_run_status": "success",
      "records_produced": 1240,
      "quarantine_count": 12
    }
  ]
}
```

---

### POST /api/v1/agents/{agent_id}/run

Trigger an on-demand run of a specific agent.

**Path param**: `agent_id` — one of:
`service_line_inference`, `idn_hierarchy`, `referral_network`, `contact_verification`,
`staffing_decomposition`, `equipment_inventory`, `publication_evidence_extractor`

**Request body** (optional):
```json
{
  "scope": "incremental",
  "limit": 1000
}
```

- `scope`: `"incremental"` (default, only unprocessed records) or `"full"` (reprocess all)
- `limit`: max records to process per run (0 = no limit)

**Response** `202 Accepted`:
```json
{
  "job_id": "agent-publication_evidence_extractor-20260327T120000Z",
  "agent_id": "publication_evidence_extractor",
  "status": "running",
  "message": "Agent started. Results written to mol_silver.publication_evidence."
}
```

**Errors**:
- `404` — agent not found
- `409` — agent already running
- `503` — LiteLLM proxy unavailable

---

### GET /api/v1/agents/{agent_id}/runs

Get run history for a specific agent, sourced from `meta.refresh_log`.

**Query params**:
- `limit` (default: 10): number of recent runs to return

**Response** `200 OK`:
```json
{
  "agent_id": "publication_evidence_extractor",
  "runs": [
    {
      "run_id": 1042,
      "started_at": "2026-03-01T00:00:00Z",
      "completed_at": "2026-03-01T00:12:00Z",
      "status": "success",
      "records_produced": 88,
      "quarantine_count": 3,
      "needs_review_count": 7
    }
  ]
}
```

---

### GET /api/v1/agents/quarantine

List quarantined records pending review (confidence < 0.5).

**Query params**:
- `agent_id` (optional): filter by agent
- `limit` (default: 50)
- `offset` (default: 0)

**Response** `200 OK`:
```json
{
  "total": 24,
  "records": [
    {
      "id": "uuid",
      "agent_name": "publication_evidence_extractor",
      "confidence_score": 0.38,
      "created_at": "2026-03-01T00:00:00Z",
      "reviewed": false
    }
  ]
}
```

---

## Ingestion CLI (unchanged contract)

The existing `python -m dk_data.ingestion.main` CLI contract is unchanged. New CMS PUF sources and API sources are added to the `SOURCES` dict and are accessible via the same `--source` flag:

```bash
python -m dk_data.ingestion.main --source cms_part_d_spending --file /data/PartD_Spending_2023.csv
python -m dk_data.ingestion.main --source europepmc
python -m dk_data.ingestion.main --source nih_reporter
```

---

## PostgREST Exposure

Schemas exposed via PostgREST (via `PGRST_DB_SCHEMAS` env var):

**Existing** (unchanged): `mol_bronze`, `mol_silver`, `mol_gold`
**Added by this PR**: `hcs_bronze`, `hcs_silver`, `hcs_gold`
**Never exposed**: `mol_raw`, `hcs_raw`, `xenon`, `meta`

Row-level security and JWT validation apply to all exposed schemas per existing PostgREST config.
