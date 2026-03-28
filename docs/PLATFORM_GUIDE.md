# dk-data Platform Guide

Comprehensive guide for developing with, accessing, and operating the dk-data platform.

---

## 1. Platform Overview

dk-data is a pharmaceutical data intelligence platform that ingests, transforms, and serves data from 80+ external sources through a REST API.

### Architecture

```
External APIs ──> Fetchers ──> Raw Layer ──> SQLMesh Transforms ──> API Layer
(PubMed, CMS,     (Python)    (PostgreSQL)   (Bronze/Silver/Gold)  (PostgREST)
 USPTO, FDA...)
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| **PostgREST** | 3000 | Auto-generated REST API from PostgreSQL views |
| **Metering Proxy** | 3001 | API key auth, rate limiting, usage tracking (sidecar on PostgREST) |
| **Job Trigger** | 8000 | FastAPI service for job orchestration, monitoring, and platform APIs |

### Environments

| | Staging | Production |
|---|---------|------------|
| **Namespace** | `dk-data-staging` | `dk-data-prod` |
| **URL** | `https://data.staging.behaviorlabs.ai` | `https://data.behaviorlabs.ai` |
| **PostgREST replicas** | 2 | 3 |
| **Job Trigger replicas** | 1 | 2 |
| **DB pool** | 10 | 20 |
| **Doppler config** | `stg` | `prd` |

### Database Schemas (Medallion Architecture)

All schemas carry a domain prefix. There are no bare `raw`, `bronze`, `silver`, or `gold` schemas in production — SQLMesh's `physical_schema_mapping` redirects model declarations to the appropriate domain schema.

| Domain | Raw | Bronze | Silver | Gold |
|--------|-----|--------|--------|------|
| **Molecules / Drug** | `mol_raw` | `mol_bronze` | `mol_silver` | `mol_gold` |
| **Healthcare / CMS** | `hcs_raw` | `hcs_bronze` | `hcs_silver` | `hcs_gold` |
| **Indications / Disease** | — | — | `ind_silver` | `ind_gold` |
| **HCP / Researchers** | — | — | `hcp_silver` | `hcp_gold` |

Infrastructure schemas: `meta` (data catalog, job tracking), `xenon` (proprietary scoring), `staging`, `mart` (legacy TAVR).

---

## 2. Quick Start (Local Development)

### Prerequisites

- Python 3.11+, Docker, Docker Compose
- `uv` (recommended) or `pip`

### Setup

```bash
# Clone and install
git clone https://github.com/data-kinetic/dk-data-FE.git
cd dk-data-FE
pip install -e ".[dev]"

# Start local services
docker compose up -d

# Initialize database (first time)
make init-db

# Run migrations
make migrate

# Verify
curl http://localhost:3030/health     # PostgREST
curl http://localhost:8000/health     # Job Trigger
```

### Running Fetchers Locally

```bash
# Run a single source
docker compose exec job-trigger python -m dk_data.ingestion.main journal_rss

# Run all sources
docker compose exec job-trigger python -m dk_data.ingestion.main --all

# Check data
docker compose exec postgres psql -U postgres -d dk_data \
  -c "SELECT COUNT(*) FROM mol_raw.journal_rss;"
```

### Running Tests

```bash
pytest tests/ -v                          # All tests
pytest tests/test_security.py -v          # Security tests
pytest -k "test_jwt" -v                   # By keyword
ruff check .                              # Linting
```

---

## 3. Adding a New Data Source

### Checklist

- [ ] Create fetcher class in `src/dk_data/ingestion/fetchers/`
- [ ] Create loader in `src/dk_data/ingestion/sources/`
- [ ] Create raw table migration in `src/dk_data/sql/migrations/`
- [ ] Register source in `fetch_data.py` and `main.py`
- [ ] Create CronJob manifest in `k8s/apps/cronjobs/base/`
- [ ] Add to `k8s/apps/cronjobs/base/kustomization.yaml`
- [ ] Add seed row to `meta.data_sources`
- [ ] Add tests
- [ ] (Optional) Create SQLMesh bronze model
- [ ] (Optional) Create API view

### Step 1: Create the Fetcher

**File:** `src/dk_data/ingestion/fetchers/my_source.py`

```python
import hashlib
import logging
from typing import Any, Dict, Optional
from .base import BaseFetcher

logger = logging.getLogger(__name__)

class MySourceFetcher(BaseFetcher):
    SOURCE_NAME = "my_source"
    BASE_URL = "https://api.example.com/v1"

    def get_latest_url(self) -> str:
        return f"{self.BASE_URL}/data"

    def fetch(self, **kwargs) -> Dict[str, Any]:
        try:
            data = self.fetch_json(f"{self.BASE_URL}/data", params={"limit": 1000})
            records = [self._normalize(r) for r in data.get("results", [])]

            content_hash = hashlib.md5(
                ",".join(sorted(r["id"] for r in records)).encode()
            ).hexdigest() if records else None

            return {"status": "success", "records": records, "hash": content_hash}
        except Exception as e:
            logger.exception(f"Fetch failed: {e}")
            return {"status": "failed", "records": [], "hash": None, "error": str(e)}

    def _normalize(self, entry: dict) -> dict:
        return {
            "id": entry["id"],
            "title": entry.get("title"),
            "date": entry.get("created_at"),
        }
```

`BaseFetcher` provides: HTTP session with retries, `fetch_json()`, `download_file()`, `calculate_hash()`.

### Step 2: Create the Loader

**File:** `src/dk_data/ingestion/sources/my_source.py`

```python
import logging
from typing import Any, Dict, List
from ..utils.database import get_connection

logger = logging.getLogger(__name__)

def load_my_source_data(records: List[Dict[str, Any]], source_hash: str = None, **kwargs) -> Dict[str, Any]:
    inserted = 0
    errors = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, r in enumerate(records):
                try:
                    body_json = json.dumps(r)
                    body_hash = hashlib.sha256(body_json.encode()).hexdigest()
                    cur.execute("""
                        INSERT INTO mol_raw.my_source (
                            request_id, request_timestamp, api_endpoint,
                            response_body, response_body_hash, response_size_bytes,
                            processed_to_bronze, ingested_at, source_id
                        ) VALUES (%s, NOW(), %s, %s, %s, %s, FALSE, NOW(), 'my_source')
                        ON CONFLICT (request_id)
                        DO UPDATE SET
                            response_body       = EXCLUDED.response_body,
                            response_body_hash  = EXCLUDED.response_body_hash,
                            processed_to_bronze = FALSE,
                            ingested_at         = NOW()
                        WHERE mol_raw.my_source.response_body_hash
                              IS DISTINCT FROM EXCLUDED.response_body_hash
                    """, (f"my_source_{r['id']}", endpoint, body_json, body_hash, len(body_json.encode())))
                    inserted += 1
                except Exception as e:
                    errors.append({"index": i, "error": str(e)})
            conn.commit()
    return {"status": "success" if not errors else "partial",
            "records_inserted": inserted, "records_failed": len(errors), "errors": errors}
```

### Step 3: Create the Migration

**File:** `src/dk_data/sql/migrations/085_my_source_raw_table.sql`

```sql
-- Use mol_raw for molecule/drug sources, hcs_raw for CMS/provider sources
CREATE TABLE IF NOT EXISTS mol_raw.my_source (
    request_id          VARCHAR(512) NOT NULL PRIMARY KEY,
    request_timestamp   TIMESTAMPTZ NOT NULL,
    api_endpoint        TEXT NOT NULL,
    api_version         VARCHAR(50),
    request_params      JSONB,
    response_status     INTEGER NOT NULL DEFAULT 200,
    response_body       JSONB NOT NULL,
    response_body_hash  VARCHAR(64),
    response_size_bytes INTEGER,
    processed_to_bronze BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_id           VARCHAR(100) NOT NULL DEFAULT 'my_source'
);

CREATE INDEX IF NOT EXISTS idx_my_source_ingested ON mol_raw.my_source(ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_my_source_hash ON mol_raw.my_source(response_body_hash);
```

Use the next available migration number. All raw tables use the JSONB envelope schema — do not create flat column tables for raw data.

### Step 4: Register the Source

**In `src/dk_data/ingestion/main.py`** (in the `SOURCES` dict):
```python
'my_source': {
    'name': 'MySource API',
    'description': 'Brief description',
    'fetcher': MySourceFetcher,
    'loader': load_my_source_data,
    'requires_file': False,
    'default_days_back': 30,  # or None for full-refresh sources
},
```

Also add the import of the fetcher and loader at the top of `main.py` alongside the existing imports.

### Step 5: Create CronJob

**File:** `k8s/apps/cronjobs/base/cronjob-fetch-my-source.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: fetch-my-source
  labels:
    app: fetch-my-source
    app.kubernetes.io/component: ingestion
    app.kubernetes.io/part-of: dk-data
spec:
  schedule: "0 14 * * *"    # Daily 2 PM UTC
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600
      template:
        metadata:
          labels:
            app: fetch-my-source
            app.kubernetes.io/component: batch-job
            app.kubernetes.io/part-of: dk-data
            team: data-platform
            service: dk-data
            product: dk-data
        spec:
          restartPolicy: Never
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            fsGroup: 1000
            seccompProfile:
              type: RuntimeDefault
          imagePullSecrets:
            - name: ghcr-credentials
          containers:
            - name: fetch-my-source
              image: ghcr.io/data-kinetic/dk-data-fe/job-trigger:latest
              command: ["python", "-m", "dk_data.ingestion.main"]
              args: ["my_source"]
              env:
                - name: POSTGRES_HOST
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_HOST
                - name: POSTGRES_PORT
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_PORT
                - name: POSTGRES_USER
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_USER
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_PASSWORD
                - name: POSTGRES_DB
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-secrets
                      key: POSTGRES_DB
                - name: OTEL_EXPORTER_OTLP_ENDPOINT
                  value: "http://alloy.infra.svc.cluster.local:4317"
                - name: OTEL_ENABLED
                  value: "true"
              resources:
                requests:
                  memory: "256Mi"
                  cpu: "100m"
                limits:
                  memory: "512Mi"
                  cpu: "300m"
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
              volumeMounts:
                - name: tmp
                  mountPath: /tmp
          volumes:
            - name: tmp
              emptyDir: {}
```

Add to `k8s/apps/cronjobs/base/kustomization.yaml`:
```yaml
resources:
  - cronjob-fetch-my-source.yaml
```

### Step 6: Seed Metadata

Add to `meta.data_sources` via SQL or migration:
```sql
INSERT INTO meta.data_sources (source_name, source_type, description, refresh_frequency, is_active)
VALUES ('my_source', 'api', 'MySource API description', 'daily', true)
ON CONFLICT (source_name) DO NOTHING;
```

If the source needs API credentials, add them to Doppler (`dk-data-applications` project).

---

## 4. Accessing Data

### PostgREST REST API

**Base URLs:**
- Production: `https://data.behaviorlabs.ai`
- Staging: `https://data.staging.behaviorlabs.ai`

**Exposed schemas:** `api`, `mol_api`, `mol_gold`, `mol_silver`, `xenon`, `meta`

#### Anonymous Access (no auth)

```bash
# Health check
curl https://data.behaviorlabs.ai/health

# Data catalog
curl https://data.behaviorlabs.ai/data_catalog
```

#### Authenticated Access (JWT)

Generate a JWT token:
```python
import jwt
from datetime import datetime, timedelta

token = jwt.encode(
    {"role": "analyst", "exp": datetime.utcnow() + timedelta(hours=24)},
    "YOUR_JWT_SECRET",  # From Doppler: PGRST_JWT_SECRET
    algorithm="HS256"
)
```

```bash
# Query targets (requires analyst role)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/targets?state=eq.CA&order=score.desc&limit=10"

# Query data sources
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/data_sources?is_active=eq.true"
```

#### PostgREST Query Operators

| Operator | Example | Meaning |
|----------|---------|---------|
| `eq` | `?state=eq.CA` | Equals |
| `neq` | `?status=neq.inactive` | Not equals |
| `gt`, `gte`, `lt`, `lte` | `?score=gt.800` | Comparisons |
| `in` | `?state=in.(CA,TX,FL)` | In set |
| `like`, `ilike` | `?name=ilike.*medical*` | Pattern match |
| `is` | `?deleted=is.null` | NULL check |
| `order` | `?order=score.desc` | Sort |
| `limit`, `offset` | `?limit=10&offset=20` | Pagination |
| `select` | `?select=id,name,score` | Column selection |

#### Database Roles

| Role | Access | When to Use |
|------|--------|------------|
| `web_anon` | `api.health`, `api.data_catalog` only | Public/anonymous requests |
| `analyst` | All `api.*` views (read-only) | Data analysis, dashboards |
| `api_user` | All schemas (read-only) | Programmatic integrations |

### From BehaviorLabs / AgentMesh (K8s Internal)

Services in approved namespaces can connect directly via cluster DNS:

```
# PostgREST (direct, bypasses metering)
postgrest.dk-data-prod.svc.cluster.local:3000

# Metering Proxy (with API key auth)
dk-data-metering-proxy.dk-data-prod.svc.cluster.local:3001
```

**Allowed namespaces** (NetworkPolicy):
- `behaviorlabs-prod`, `behaviorlabs-staging`
- `agentmesh-prod`, `agentmesh-staging`
- `infra` (monitoring)

**Example from a BehaviorLabs pod:**
```bash
curl http://postgrest.dk-data-prod.svc.cluster.local:3000/data_catalog
```

**With JWT auth:**
```python
import httpx

client = httpx.Client(
    base_url="http://postgrest.dk-data-prod.svc.cluster.local:3000",
    headers={"Authorization": f"Bearer {jwt_token}"}
)
response = client.get("/targets", params={"state": "eq.CA"})
data = response.json()
```

### Metering Proxy API Keys

For external-facing integrations, use API keys via the metering proxy:

| Consumer | Allowed Schemas | Rate Limit |
|----------|----------------|------------|
| `behavior-labs-ai` | mart, api, mol_api, scoring | 500 req/min |
| `carbon-5` | mart, api, bronze, silver, gold | 500 req/min |
| `dk-os` | api, meta | 200 req/min |
| `internal` | all | unlimited |

API keys are managed in `k8s/apps/metering-proxy/base/configmap.yaml`.

---

## 5. Connecting to the Database

### Connection Details

| Environment | Host (in-cluster) | Port | Database |
|-------------|-------------------|------|----------|
| Production | `postgresql.infra.svc.cluster.local` | 5432 | `dk_data` |
| Staging | `postgresql.infra-staging.svc.cluster.local` | 5432 | `dk_data` |
| Local | `localhost` | 5433 | `dk_data` |

Credentials are in Doppler (`dk-data-applications` project, `prd`/`stg` config).

### pgAdmin / DBeaver (via SSH Tunnel)

Since the database is inside the Kubernetes cluster, you need an SSH tunnel:

**Step 1: Start the K8s API tunnel** (if not already running)
```bash
cd /path/to/dk-alchemy/scripts/penguin
./kubeconfig-k3s.sh tunnel
# Keep this terminal open
```

**Step 2: Port-forward to PostgreSQL**
```bash
# In another terminal
export KUBECONFIG=~/.kube/k3s-master-1.yaml

# Production database
kubectl port-forward -n infra svc/postgresql 5432:5432

# Or staging database
kubectl port-forward -n infra-staging svc/postgresql 5433:5432
```

**Step 3: Connect pgAdmin/DBeaver**
```
Host: localhost
Port: 5432 (prod) or 5433 (staging)
Database: dk_data
Username: <from Doppler POSTGRES_USER>
Password: <from Doppler POSTGRES_PASSWORD>
```

### Direct SSH + psql

```bash
# One-liner via SSH jump
ssh k3s-master "kubectl exec -n dk-data-prod deploy/job-trigger -- \
  python3 -c \"import psycopg2, os; \
  conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], \
  port=os.environ['POSTGRES_PORT'], user=os.environ['POSTGRES_USER'], \
  password=os.environ['POSTGRES_PASSWORD'], dbname=os.environ['POSTGRES_DB']); \
  cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM raw.pubmed'); \
  print(cur.fetchone()); conn.close()\""
```

### SSH Config (required)

Ensure `~/.ssh/config` has:
```
Host penguin
    HostName 192.168.10.8
    User ubuntu
    IdentityFile ~/.ssh/id_rsa_penguin

Host k3s-master
    HostName 10.0.0.11
    User ubuntu
    ProxyJump penguin
    IdentityFile ~/.ssh/id_rsa_k3s
```

---

## 6. CI/CD Pipeline

### Build Flow

```
Push to main
  --> build-deploy.yaml
      --> Build Docker image
      --> Push ghcr.io/data-kinetic/dk-data-fe/job-trigger:main-<sha>
      --> Update k8s/overlays/staging/kustomization.yaml
      --> Commit to main
  --> promote-to-prod.yaml (on build success)
      --> Re-tag image: main-<sha> --> prod-<sha>
      --> Update k8s/overlays/prod/kustomization.yaml
      --> Commit to main
  --> ArgoCD detects change, syncs to cluster
```

### Image Tags

| Tag Pattern | When Used |
|------------|-----------|
| `main-<sha>` | Staging (auto, on push to main) |
| `staging-<sha>` | Staging (on push to staging branch) |
| `prod-<sha>` | Production (auto-promoted from main) |
| `latest` | Latest main build (for base image references) |

### ArgoCD

dk-data is deployed via ArgoCD applications:
- `dk-data-prod` — tracks `k8s/overlays/prod/` on main branch
- `dk-data-staging` — tracks `k8s/overlays/staging/` on staging branch
- `dk-data-bootstrap-prod` / `dk-data-bootstrap-staging` — infrastructure

**Force sync:**
```bash
ssh k3s-master "kubectl annotate application dk-data-prod -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite"
```

### PR Testing

PRs trigger `.github/workflows/ci.yaml`:
1. Lint (`ruff check .`)
2. Test (`pytest` with PostgreSQL 16 service container)
3. Coverage report (min 15%)

---

## 7. Monitoring & Observability

### Grafana

**URL:** `https://grafana.behaviorlabs.ai`

**Dashboards:**
- `dk-data-overview` — API health, data freshness, molecule pipeline, resources
- `dk-data-cronjobs` — CronJob status, failures, durations
- `postgrest-overview` — PostgREST request rates, latencies
- `job-trigger-overview` — Job trigger service metrics

### Prometheus Metrics

Metrics exported at:
- Job Trigger: `http://job-trigger:8000/metrics`
- Metering Proxy: `http://postgrest:9090/metrics`

Key metrics:
- `http_requests_total` — API request count
- `batch_job_duration_seconds` — Job execution time
- `dk_data_source_staleness_hours` — Data freshness per source
- `dk_pipeline_records_processed_total` — Pipeline throughput
- `dk_quarantine_count` — Molecules flagged for review

### Alerts (PrometheusRule)

| Alert | Condition | Severity |
|-------|-----------|----------|
| `DataSourceStale` | No refresh in 48h | warning |
| `DataSourceCriticallyStale` | No refresh in 7d | critical |
| `APIHighErrorRate` | >5% 5xx errors for 5m | critical |
| `APIUnavailable` | Health probe failing 2m | critical |
| `BatchJobFailed` | >2 failures in 1h | warning |
| `MoleculeTransformStale` | No transform in 48h | warning |

### OpenTelemetry Tracing

Traces are sent to Alloy (Grafana Agent) at `alloy.infra.svc.cluster.local:4317`.

Configuration in job-trigger deployment:
```yaml
OTEL_EXPORTER_OTLP_ENDPOINT: "http://alloy.infra.svc.cluster.local:4317"
OTEL_ENABLED: "true"
```

Traces include: HTTP requests, database queries, job execution spans.

### Health Endpoints

| Endpoint | Service | Purpose |
|----------|---------|---------|
| `GET /health` | Job Trigger (8000) | Service + DB connectivity |
| `GET /health` | PostgREST (3000) | PostgREST status |
| `GET /health` | Metering Proxy (3001) | Proxy health |
| `GET /ready` | Metering Proxy (3001) | Readiness (upstream check) |
| `GET /api/v1/monitoring/freshness` | Job Trigger | Data source freshness |
| `GET /api/v1/monitoring/sources` | Job Trigger | Source status |

---

## 8. Configuration

### Doppler Secrets

**Project:** `dk-data-applications`
**Configs:** `dev` (local), `stg` (staging), `prd` (production)

| Secret | Purpose |
|--------|---------|
| `POSTGRES_HOST` | Database hostname |
| `POSTGRES_PORT` | Database port |
| `POSTGRES_USER` | Database username |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_DB` | Database name |
| `POSTGREST_PASSWORD` | PostgREST authenticator role password |
| `JWT_SECRET` | JWT signing secret (min 256-bit) |

Add new secrets via Doppler CLI:
```bash
doppler secrets set MY_SOURCE_API_KEY "sk-..." --project dk-data-applications --config prd
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LOG_LEVEL` | `info` | Logging level |
| `LOG_FORMAT` | `json` | Log format (`json` or `console`) |
| `OTEL_ENABLED` | `true` | Enable OpenTelemetry tracing |
| `BATCH_SIZE` | `100` | Records per batch in molecule pipeline |
| `K8S_NAMESPACE` | (from field) | Current Kubernetes namespace |

---

## 9. Troubleshooting

### Common Issues

**502 on `data.behaviorlabs.ai`**
- The metering-proxy sidecar is down. Check PostgREST pod has 2 containers:
  ```bash
  ssh k3s-master "kubectl get pods -n dk-data-prod -l app=postgrest -o jsonpath='{.items[*].spec.containers[*].name}'"
  ```
- Expected: `postgrest metering-proxy`

**CronJob CreateContainerConfigError**
- Missing `runAsUser: 1000` in security context. All CronJobs using the job-trigger image need it.

**Staging fetchers failing with "relation does not exist"**
- Database migrations not applied. Run:
  ```bash
  ssh k3s-master "kubectl exec -n dk-data-staging deploy/job-trigger -- python -m dk_data.scripts.run_migrations"
  ```

**OTLP traces UNAVAILABLE**
- Alloy uses hostNetwork. Check NetworkPolicy allows egress to `10.0.0.0/24:4317`.

**ArgoCD OutOfSync**
- Force refresh:
  ```bash
  ssh k3s-master "kubectl annotate application dk-data-prod -n argocd argocd.argoproj.io/refresh=hard --overwrite"
  ```

**DrugBank seed BadZipFile**
- Git LFS file not fetched. Ensure CI has `lfs: true` in checkout step.
- Check locally: `file data/drugbank/drugbank_all_full_database.xml.zip` (should say "Zip archive data", not "ASCII text")

### Useful Commands

```bash
# Check all pod status
ssh k3s-master "kubectl get pods -n dk-data-prod --field-selector=status.phase!=Succeeded"

# View CronJob schedules
ssh k3s-master "kubectl get cronjobs -n dk-data-prod -o custom-columns='NAME:.metadata.name,SCHEDULE:.spec.schedule,LAST:.status.lastScheduleTime'"

# Check recent job failures
ssh k3s-master "kubectl get pods -n dk-data-prod --field-selector=status.phase=Failed"

# View job-trigger logs
ssh k3s-master "kubectl logs -n dk-data-prod deploy/job-trigger --tail=50"

# Run migrations
ssh k3s-master "kubectl exec -n dk-data-prod deploy/job-trigger -- python -m dk_data.scripts.run_migrations"

# Query database
ssh k3s-master 'kubectl exec -n dk-data-prod deploy/job-trigger -- python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ[\"POSTGRES_HOST\"], port=os.environ[\"POSTGRES_PORT\"],
    user=os.environ[\"POSTGRES_USER\"], password=os.environ[\"POSTGRES_PASSWORD\"],
    dbname=os.environ[\"POSTGRES_DB\"])
cur = conn.cursor()
cur.execute(\"SELECT source_name, last_successful_refresh FROM meta.data_sources LIMIT 5\")
for r in cur.fetchall(): print(r)
conn.close()
"'
```

---

## 10. Data Source Inventory

See `DATA_LOADERS.md` for the full per-source reference including rate limits, credentials, and loader invocation.

### Molecule / Drug Sources (28)

| Source | Frequency | Raw Table |
|--------|-----------|-----------|
| PubMed | Daily | `mol_raw.pubmed` |
| Europe PMC | Daily | `mol_raw.europepmc` |
| OpenAlex CI | Daily | `mol_raw.openalex_ci` |
| Journal RSS | Daily | `mol_raw.journal_rss` |
| Medical News | Daily | `mol_raw.medical_news` |
| NIH Reporter | Daily | `mol_raw.nih_reporter` |
| SEC EDGAR | Daily | `mol_raw.sec_edgar` |
| EMA Regulatory | Weekly | `mol_raw.ema` |
| HTA Bodies | Weekly | `mol_raw.hta_decisions` |
| USPTO Patents | Weekly | `mol_raw.uspto_patents` |
| USPTO CI | Weekly | `mol_raw.uspto_ci` |
| USPTO Trademarks | Weekly | `mol_raw.uspto_trademarks` |
| EUIPO Trademarks | Weekly | `mol_raw.euipo_trademarks` |
| EUIPO Designs | Weekly | `mol_raw.euipo_designs` |
| EPO Patents | Weekly | `mol_raw.epo_patents` |
| UniProt | Weekly | `mol_raw.uniprot` |
| PDB Structures | Weekly | `mol_raw.pdb` |
| ORCID | Weekly | `mol_raw.orcid` |
| KEGG Drug | Weekly | `mol_raw.kegg_drug` |
| DrugBank | Monthly | `mol_raw.drugbank` |
| BindingDB | Monthly | `mol_raw.bindingdb` |
| SIDER | Monthly | `mol_raw.sider` |
| WHO ICD | Monthly | `mol_raw.who_icd` |
| RxNorm | Monthly | `mol_raw.rxnorm` |
| WHO INN | Monthly | `mol_raw.who_inn` |
| PharmGKB | Monthly | `mol_raw.pharmgkb` |
| TDC ADMET | Monthly | `mol_raw.tdc_admet` |
| Cochrane | Monthly | `mol_raw.cochrane_reviews` |

### CMS / Healthcare Sources (50+)

19 API-based CMS sources (`hcs_raw.*`) + 30 CMS PUF file downloads + 5 legacy file sources. See `DATA_LOADERS.md` for the full list.

### CronJob Schedule

| CronJob | Schedule | What runs |
|---------|----------|-----------|
| `cronjob-mol-fetch-daily` | 2 AM UTC daily | PubMed, EuropePMC, OpenAlex, Journal RSS, Medical News, NIH Reporter, SEC EDGAR |
| `cronjob-mol-fetch-weekly` | 3 AM UTC Sunday | EMA, HTA, USPTO, EUIPO, EPO, UniProt, PDB, ORCID, KEGG Drug |
| `cronjob-mol-fetch-monthly` | 2–11 AM UTC 1st | BindingDB, SIDER, WHO ICD, RxNorm, WHO INN, PharmGKB, TDC ADMET, DrugBank, Cochrane |
| `cronjob-mol-transform` | 6 AM UTC daily | SQLMesh bronze → silver → gold |
| `cronjob-cms-all` | Weekly | All CMS PUF file downloads |
| Per-source CMS CronJobs | Monthly (1st) | 19 individual CMS API sources |
