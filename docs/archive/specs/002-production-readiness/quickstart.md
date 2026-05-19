# Quickstart: Production Readiness Migration

**Feature**: 002-production-readiness
**Date**: 2026-01-20
**Audience**: Developers and operators migrating dk-data-fe to production

## Prerequisites

Before starting, ensure you have:

- [ ] Access to dk-alchemy Kubernetes cluster (`kubectl` configured)
- [ ] Access to Doppler dashboard (`doppler login` completed)
- [ ] Git repository write access (for history rewrite)
- [ ] Local development environment (`uv`, Docker, Python 3.11+)

## Phase 1: Security Hardening (Day 1-2)

### 1.1 Set Up Doppler Secrets

```bash
# Install Doppler CLI if needed
brew install dopplerhq/cli/doppler

# Login to Doppler
doppler login

# Set up the dk-infrastructure project
doppler setup --project dk-infrastructure --config prod

# Add required secrets
doppler secrets set POSTGRES_HOST "postgres.postgres.svc.cluster.local"
doppler secrets set POSTGRES_PORT "5432"
doppler secrets set POSTGRES_USER "app_user"
doppler secrets set POSTGRES_PASSWORD "$(openssl rand -base64 32)"
doppler secrets set POSTGRES_DB "edwards_tavr"
doppler secrets set PGRST_JWT_SECRET "$(openssl rand -base64 32)"

# Optional: Add Anthropic API key for enrichment
doppler secrets set ANTHROPIC_API_KEY "sk-ant-..."

# Verify secrets are set
doppler secrets
```

### 1.2 Create Doppler Service Token

```bash
# Create service token for Kubernetes
doppler configs tokens create \
  --project dk-infrastructure \
  --config prod \
  --name "dk-data-fe-prod" \
  --plain > /tmp/doppler-token.txt

# Create Kubernetes secret (in dk-data-fe-prod namespace)
kubectl create namespace dk-data-fe-prod --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic doppler-token-dk-data-fe \
  --namespace dk-data-fe-prod \
  --from-literal=serviceToken="$(cat /tmp/doppler-token.txt)"

# Clean up
rm /tmp/doppler-token.txt
```

### 1.3 Update PostgREST Role Permissions

```bash
# Connect to PostgreSQL
kubectl exec -it postgres-0 -n postgres -- psql -U postgres -d edwards_tavr

# Run the role restriction script
\i /path/to/role-restrictions.sql
```

```sql
-- role-restrictions.sql
-- Restrict web_anon to health endpoints only
REVOKE ALL ON SCHEMA api FROM web_anon;
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.health TO web_anon;
GRANT SELECT ON api.data_catalog TO web_anon;

-- Verify permissions
\dp api.*
```

## Phase 2: Codebase Cleanup (Day 3-4)

### 2.1 Remove Duplicate Files

```bash
# From repository root
cd /Users/nicholas/Code/dk-data-fe

# Verify duplicates (dry run)
diff -r scripts/ src/dk_data/scripts/ 2>/dev/null || echo "Differences found"

# Remove root-level scripts directory
rm -rf scripts/

# Update docker-compose volume mounts
# Edit src/dk_data/docker-compose.yml:
# Change: - ../../scripts:/app/scripts:ro
# To: Remove this line (scripts now in src/dk_data/scripts/)
```

### 2.2 Git History Rewrite

⚠️ **Warning**: This rewrites git history. Coordinate with all team members first.

```bash
# Create backup branch
git branch backup-before-cleanup-$(date +%Y%m%d)
git push origin backup-before-cleanup-$(date +%Y%m%d)

# Install git-filter-repo if needed
brew install git-filter-repo

# Step 1: Remove data files from history
git filter-repo --path data/ --invert-paths --force

# Step 2: Remove logs from history
git filter-repo --path logs/ --invert-paths --force

# Step 3: Verify size reduction
git count-objects -vH

# Step 4: Force push (COORDINATE WITH TEAM FIRST)
git push --force --all
git push --force --tags
```

### 2.3 Upload Data to MinIO

```bash
# Configure MinIO CLI
mc alias set dk-minio https://minio.dk-alchemy.example.com admin <password>

# Create bucket for dk-data-fe
mc mb dk-minio/dk-data-fe

# Upload existing data files
mc cp --recursive data/raw/ dk-minio/dk-data-fe/raw/

# Verify upload
mc ls dk-minio/dk-data-fe/raw/
```

### 2.4 Update .gitignore

```bash
cat >> .gitignore << 'EOF'

# Data files (store in MinIO)
/data/
!/data/README.md

# Log files
/logs/
*.log

# Environment files with secrets
.env
.env.local
.env.*.local
EOF

git add .gitignore
git commit -m "Update .gitignore for data and log files"
```

## Phase 3: Observability Integration (Day 5-6)

### 3.1 Add OpenTelemetry Dependencies

```bash
# Update pyproject.toml
cat >> pyproject.toml << 'EOF'

# Observability dependencies
opentelemetry-api = ">=1.20.0"
opentelemetry-sdk = ">=1.20.0"
opentelemetry-exporter-otlp = ">=1.20.0"
opentelemetry-instrumentation-fastapi = ">=0.41b0"
opentelemetry-instrumentation-psycopg2 = ">=0.41b0"
opentelemetry-instrumentation-requests = ">=0.41b0"
structlog = ">=24.0.0"
prometheus-client = ">=0.19.0"
EOF

# Update lock file
uv lock
uv sync
```

### 3.2 Create Observability Module

Create `src/dk_data/observability/__init__.py`:

```python
"""OpenTelemetry instrumentation for dk-data-fe."""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def setup_telemetry(service_name: str) -> None:
    """Initialize OpenTelemetry with OTLP exporter."""
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "dk-data-fe",
        "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
    })

    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "alloy.monitoring:4317")
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
```

### 3.3 Deploy ServiceMonitor

```bash
# Apply ServiceMonitor for Prometheus scraping
kubectl apply -f specs/002-production-readiness/contracts/service-monitor.yaml
```

### 3.4 Deploy Alert Rules

```bash
# Apply PrometheusRule for alerting
kubectl apply -f specs/002-production-readiness/contracts/alert-rules.yaml

# Verify rules are loaded
kubectl get prometheusrules -n dk-data-fe-prod
```

## Phase 4: GitOps Restructuring (Day 7-8)

### 4.1 Create New Directory Structure

```bash
# Create k8s directory structure
mkdir -p k8s/postgrest/{base,overlays/{prod,staging}}
mkdir -p k8s/job-trigger/{base,overlays/{prod,staging}}
mkdir -p k8s/cronjobs/{base,overlays/{prod,staging}}

# Move existing manifests
mv .gitops/base/postgrest/* k8s/postgrest/base/
mv .gitops/base/ingestion/job-trigger-* k8s/job-trigger/base/
mv .gitops/base/ingestion/cronjob-* k8s/cronjobs/base/
mv .gitops/base/catalog/* k8s/cronjobs/base/

# Create overlay kustomizations
# (See generated kustomization.yaml files in each overlay)
```

### 4.2 Create ArgoCD Applications

```bash
# Create app-of-apps structure
mkdir -p .gitops/prod/apps .gitops/staging/apps

# Create application manifests
# (See contracts/argocd-apps.yaml for templates)
```

### 4.3 Add Bootstrap to dk-alchemy

In the dk-alchemy repository:

```bash
cd /Users/nicholas/Code/dk-alchemy

# Create bootstrap application
cat > .gitops/external/dk-data-fe.yaml << 'EOF'
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: dk-data-fe-bootstrap-prod
  namespace: argocd
spec:
  project: dk-data-fe-bootstrap
  source:
    repoURL: https://github.com/data-kinetic/dk-data-fe.git
    targetRevision: main
    path: .gitops/prod/apps
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF

git add .gitops/external/dk-data-fe.yaml
git commit -m "Add dk-data-fe bootstrap application"
git push
```

## Verification Checklist

### Security (SC-001, SC-006, SC-007)

```bash
# Check for secrets in repository
gitleaks detect --source . --verbose

# Verify Doppler integration
kubectl get secret dk-data-fe-secrets -n dk-data-fe-prod -o yaml

# Test unauthenticated access (should return 401)
curl -i https://api.dk-data-fe.example.com/targets
# Expected: HTTP/2 401

# Test health endpoint (should work without auth)
curl https://api.dk-data-fe.example.com/health
# Expected: {"status": "ok"}
```

### Codebase (SC-002, SC-003)

```bash
# Verify repository size
git count-objects -vH
# Expected: < 10 MB

# Check for duplicates
find . -name "*.py" -path "*/scripts/*" | wc -l
# Expected: Only in src/dk_data/scripts/
```

### Observability (SC-004)

```bash
# Check metrics in Grafana
# Navigate to: https://grafana.dk-alchemy.example.com
# Dashboard: dk-data-fe API Health
# Verify: Request metrics visible within 60 seconds

# Check logs in Loki
# Query: {namespace="dk-data-fe-prod"}
```

### GitOps (SC-005)

```bash
# Verify ArgoCD sync
argocd app get dk-data-fe-postgrest
# Expected: Synced, Healthy

# Test sync time
git commit --allow-empty -m "Test sync timing"
git push
# Measure time until ArgoCD shows synced (< 5 minutes)
```

## Rollback Procedures

### Secrets Rollback

```bash
# If Doppler has issues, temporarily use static secrets
kubectl create secret generic dk-data-fe-secrets \
  --namespace dk-data-fe-prod \
  --from-literal=POSTGRES_PASSWORD="emergency-password" \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Git History Rollback

```bash
# Restore from backup branch
git checkout backup-before-cleanup-YYYYMMDD
git branch -D main
git checkout -b main
git push --force origin main
```

### ArgoCD Rollback

```bash
# Rollback to previous sync
argocd app rollback dk-data-fe-postgrest 1
```

## Support Contacts

- **On-call**: #dk-data-fe-alerts Slack channel
- **Documentation**: https://docs.example.com/dk-data-fe
- **Runbooks**: https://docs.example.com/runbooks/dk-data-fe
