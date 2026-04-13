# Contract: Warehouse Surface Changes

> **⚠ DRAFT — CONTRACTS FOLLOW CODE**
>
> Endpoint lists, column shapes, and auth behaviors described below are the **intended** post-migration state. Once migrations 215–218 are actually written at T067/T071/T073/T077, diff the written SQL against this contract and **update this file to match the code** (not the reverse). See tasks T161 (contracts sync) and T163 (verification artifacts).


## PostgREST (via metering proxy)

Base URL: `https://data.behaviorlabs.ai`
Authentication: `Authorization: Bearer dk_data_{alias}_{suffix}` (required for every request)

### After migration 215 (CI view rename)

New prefixed endpoints (via `Accept-Profile: mol_api` or `ip_api`):

```
GET /pubmed_publications            (profile: mol_api)
GET /openalex_publications          (profile: mol_api)
GET /ema_regulatory_decisions       (profile: mol_api)
GET /journal_articles               (profile: mol_api)
GET /hta_decisions                  (profile: mol_api)
GET /cochrane_reviews               (profile: mol_api)
GET /medical_news                   (profile: mol_api)
GET /sec_filings                    (profile: mol_api)

GET /uspto_patents                  (profile: ip_api)
GET /epo_patents                    (profile: ip_api)
```

Deprecated aliases (in `api` schema) still work during 30-day observation window:

```
GET /pubmed_publications            (default profile: api)    — ALIAS, sunset after migration complete
GET /openalex_publications          (default profile: api)    — ALIAS
[... 8 more aliases]
```

### After migration 216 (missing mol_api views)

```
GET /boxed_warnings?molecule_id=eq.{id}       (profile: mol_api)
GET /contraindications?molecule_id=eq.{id}    (profile: mol_api)
GET /competitive_scores?molecule_id=eq.{id}   (profile: mol_api)
GET /companies?id=eq.{id}                     (profile: mol_api)
GET /publications?molecule_id=eq.{id}         (profile: mol_api)  — UNION of pubmed + openalex
```

### After migration 217 (resolve function grants)

```
GET  /rpc/resolve_molecule?name_or_id={q}     (profile: mol_silver)
POST /rpc/resolve_drug_product                (profile: mol_silver)
POST /rpc/resolve_target                      (profile: mol_silver)
POST /rpc/resolve_condition                   (profile: ind_silver)
POST /rpc/resolve_company                     (profile: mol_silver)
POST /rpc/resolve_provider                    (profile: hcs_silver)
POST /rpc/resolve_facility                    (profile: hcs_silver)
POST /rpc/resolve_researcher                  (profile: hcp_silver)
POST /rpc/resolve_patent                      (profile: ip_silver)
POST /rpc/resolve_trademark                   (profile: ip_silver)
POST /rpc/resolve_design                      (profile: ip_silver)
```

### After migration 218 (drop web_anon)

- Any request without an `Authorization` header returns `401 Unauthorized`
- `GET /health` also returns 401 (no carve-out — probes are TCP only)

---

## FastAPI `/data-platform/*` (US-15 adds JWT dependency at router level)

Base URL: `https://data.behaviorlabs.ai/data-platform`
Authentication: `Authorization: Bearer <jwt>` (JWT minted by metering proxy)

All 34 existing routes continue to work, but now require a valid JWT:

```
GET    /data-platform/molecules/search
POST   /data-platform/resolve
GET    /data-platform/molecules/{id}
GET    /data-platform/molecules/{id}/safety
GET    /data-platform/molecules/{id}/evidence
GET    /data-platform/resolution-queue
POST   /data-platform/resolution-queue/{item_id}/action
POST   /data-platform/resolution-queue/bulk-approve
GET    /data-platform/resolution-queue/{item_id}/potential-duplicates
GET    /data-platform/resolution-queue/stats
GET    /data-platform/status
POST   /data-platform/refresh/gold
POST   /data-platform/ingest/{source}
POST   /data-platform/pipeline/run
GET    /data-platform/competitive-landscape
GET    /data-platform/company-pipeline/{company}
GET    /data-platform/gold/molecule-profiles
GET    /data-platform/gold/safety-signals
GET    /data-platform/gold/lifecycle-stages
GET    /data-platform/gold/data-quality
GET    /data-platform/scheduler/status
GET    /data-platform/scheduler/jobs
POST   /data-platform/scheduler/trigger/{tier}
PUT    /data-platform/scheduler/schedule/{source}
POST   /data-platform/sources/register
POST   /data-platform/dynamic-transform
POST   /data-platform/schema/detect
POST   /data-platform/models/generate
GET    /data-platform/transformation-sources
GET    /data-platform/transformation-sources/{source_name}
DELETE /data-platform/transformation-sources/{source_name}
POST   /data-platform/transformation-sources/{source_name}/enable
POST   /data-platform/transform-raw/{source}
```

New routes added by US-5 (resolve wrappers):

```
POST /data-platform/conditions/resolve
POST /data-platform/companies/resolve
POST /data-platform/providers/resolve
POST /data-platform/facilities/resolve
POST /data-platform/researchers/resolve
POST /data-platform/patents/resolve
POST /data-platform/trademarks/resolve
```

### Auth contract

```python
# src/dk_data/api/dependencies/auth.py
async def verify_jwt(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    try:
        claims = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    if claims.get("role") not in {"analyst", "api_user"}:
        raise HTTPException(403, f"Role not allowed")
    return claims
```

```python
# src/dk_data/api/routes/data_platform.py
router = APIRouter(
    prefix="/data-platform",
    tags=["data-platform"],
    dependencies=[Depends(verify_jwt)],  # ALL routes protected
)
```

---

## Metering proxy (`consumers.yaml`)

### Consumer registry schema

```yaml
consumers:
  <consumer-name>:
    alias: <short-form>
    allowed_schemas: [<schema>, ...]  # MUST be explicit list, NEVER ["*"] for external
    rpm_limit: <int>
    tier: standard | high | unlimited
    api_keys: [<provisioned-key>, ...]
```

### Gateway request flow

```
client request
   ↓
[1] proxy validates Authorization: Bearer dk_data_{alias}_{suffix}
       → unknown key → 401 Unauthorized
   ↓
[2] proxy looks up consumer from alias
       → unknown consumer → 401
   ↓
[3] proxy checks requested schema against consumer.allowed_schemas
       → not in allowlist → 403 Forbidden
   ↓
[4] proxy checks rate limit (rpm_limit window)
       → exceeded → 429 Too Many Requests
   ↓
[5] proxy mints short-lived JWT (5 min expiry, role claim = api_user or analyst per consumer tier)
   ↓
[6] proxy forwards to PostgREST or FastAPI with Bearer <jwt>
   ↓
[7] proxy audit-logs: {consumer_id, resource, status, latency_ms, ts}
   ↓
response to client
```

---

## Metrics endpoints

All three MUST be scraped by Prometheus with `job="dk-data-platform"` label.

```
GET  http://job-trigger:8000/metrics              (Prometheus text format)
GET  http://dk-data-metering-proxy:3001/metrics   (Prometheus text format)  — NEEDS annotation
GET  http://batch-api:8001/metrics                 (Prometheus text format)  — NEEDS annotation
```

Required k8s annotation (on deployments, or equivalent ServiceMonitor selector):

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "<port>"
    prometheus.io/path: "/metrics"
```

The metric names emitted MUST match every dashboard panel reference. A CI check (FR-045) fails the build on any mismatch.

---

## Backward compatibility

- Deprecated `api.*` aliases live for 30 days after last telemetry-verified consumer migration (FR-028)
- Client v0.x → v1.0 may include breaking changes; client v1.x → v1.y is additive-only
- Warehouse OpenAPI schema fingerprint tracked; client warns on mismatch at startup
