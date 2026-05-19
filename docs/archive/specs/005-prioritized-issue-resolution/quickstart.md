# Quickstart: Prioritized Issue Resolution

**Feature**: 005-prioritized-issue-resolution
**Date**: 2026-01-30

## Prerequisites

Before implementing this feature, ensure:

1. **dk-alchemy cluster is operational**
   ```bash
   kubectl get nodes
   kubectl get pods -n infra
   ```

2. **Doppler is configured with JWT secret**
   ```bash
   # Verify Doppler project exists
   doppler projects

   # Verify JWT secret is set (should be 32+ characters)
   doppler secrets get PGRST_JWT_SECRET --project dk-data --config stg
   ```

3. **PostgreSQL is accessible**
   ```bash
   # From within cluster
   kubectl run -it --rm pg-test --image=postgres:16 -- \
     psql -h postgresql.infra.svc.cluster.local -U postgres -c "SELECT 1"
   ```

4. **GitHub Actions has GHCR permissions**
   - Repository Settings → Actions → General → Workflow permissions
   - Enable "Read and write permissions"

## Local Development

### 1. Start Local Environment

```bash
# Start PostgreSQL and PostgREST
docker-compose up -d

# Verify services
docker-compose ps
curl http://localhost:3030/health
```

### 2. Run Database Initialization

```bash
# Execute db-init SQL manually
docker-compose exec postgres psql -U postgres -d dk_data -f /path/to/init.sql

# Or run the k8s job locally via docker
docker run --rm \
  -e PGHOST=host.docker.internal \
  -e PGPORT=5432 \
  -e PGPASSWORD=postgres \
  postgres:16 \
  psql -U postgres -c "SELECT * FROM pg_roles"
```

### 3. Test Security Locally

```bash
# Test anonymous access (should work for health)
curl http://localhost:3030/health

# Test anonymous access to protected endpoint (should fail)
curl http://localhost:3030/targets
# Expected: {"message":"permission denied for view targets"...}

# Test with valid JWT
export JWT_SECRET="your-32-character-or-longer-secret"
export TOKEN=$(python3 -c "
import jwt
import datetime
token = jwt.encode({
    'role': 'analyst',
    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
}, '$JWT_SECRET', algorithm='HS256')
print(token)
")

curl -H "Authorization: Bearer $TOKEN" http://localhost:3030/targets
```

### 4. Run Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/dk_data --cov-report=html

# Run linting
ruff check .
```

## Cluster Deployment

### 1. Verify CRDs (for observability)

```bash
# Check if Prometheus Operator CRDs exist
kubectl get crd servicemonitors.monitoring.coreos.com 2>/dev/null && echo "ServiceMonitor CRD: Available" || echo "ServiceMonitor CRD: NOT AVAILABLE"
kubectl get crd prometheusrules.monitoring.coreos.com 2>/dev/null && echo "PrometheusRule CRD: Available" || echo "PrometheusRule CRD: NOT AVAILABLE"
```

If CRDs are not available, keep observability resources commented in `k8s/base/kustomization.yaml`.

### 2. Deploy to Staging

```bash
# Ensure you're on staging branch
git checkout staging

# Apply changes
kubectl apply -k k8s/overlays/staging --dry-run=client
kubectl apply -k k8s/overlays/staging

# Watch deployment
kubectl get pods -n dk-data-staging -w

# Check db-init job
kubectl logs -n dk-data-staging job/db-init

# Check PostgREST logs
kubectl logs -n dk-data-staging -l app=postgrest
```

### 3. Verify Security

```bash
# Get staging URL
export STAGING_URL="https://data.preview.behaviorlabs.ai"

# Test health endpoint (should work without auth)
curl -s "$STAGING_URL/health" | jq

# Test anonymous access to protected endpoint (should fail)
curl -s "$STAGING_URL/targets"
# Expected: 401 or 403

# Test with forged token (empty secret)
FORGED_TOKEN=$(python3 -c "
import jwt
import datetime
token = jwt.encode({
    'role': 'analyst',
    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
}, '', algorithm='HS256')
print(token)
")
curl -s -H "Authorization: Bearer $FORGED_TOKEN" "$STAGING_URL/targets"
# Expected: 401 (JWT verification failed)
```

### 4. Verify Database Initialization

```bash
# Connect to database
kubectl exec -it -n infra deploy/postgresql -- psql -U postgres -d dk_data

# Check roles
\du

# Check schemas
\dn

# Check API views
\dv api.*

# Check permissions
\dp api.health
\dp api.targets
```

### 5. Verify CI/CD Pipeline

```bash
# Create a test PR
git checkout -b test-ci-pipeline
echo "# Test" >> README.md
git add README.md
git commit -m "test: CI pipeline verification"
git push -u origin test-ci-pipeline

# Create PR via GitHub CLI
gh pr create --title "Test CI Pipeline" --body "Verifying CI workflow"

# Check workflow status
gh run list --workflow=ci.yaml
```

## Troubleshooting

### db-init Job Fails

```bash
# Check job status
kubectl describe job/db-init -n dk-data-staging

# Check pod logs
kubectl logs -n dk-data-staging -l job-name=db-init

# Common issues:
# 1. PGPASSWORD not set - Check Doppler secret sync
# 2. SQL syntax error - Review heredoc escaping
# 3. Role already exists - Job should be idempotent, check DO $$ blocks
```

### PostgREST Reports "0 Relations"

```bash
# Check if views exist
kubectl exec -it -n infra deploy/postgresql -- \
  psql -U postgres -d dk_data -c "\dv api.*"

# Check PostgREST config
kubectl get configmap postgrest-config -n dk-data-staging -o yaml

# Restart PostgREST to reload schema
kubectl rollout restart deployment/postgrest -n dk-data-staging
```

### JWT Authentication Fails

```bash
# Check JWT secret is set
kubectl get secret dk-data-secrets -n dk-data-staging -o jsonpath='{.data.PGRST_JWT_SECRET}' | base64 -d | wc -c
# Should be >= 32 characters

# Check PostgREST environment
kubectl exec -it -n dk-data-staging deploy/postgrest -- env | grep JWT

# Decode and verify JWT token
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq
```

### ServiceMonitor Not Working

```bash
# Check if CRDs exist
kubectl get crd | grep monitoring

# Check if ServiceMonitor is applied
kubectl get servicemonitor -n dk-data-staging

# Check Prometheus targets
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Open http://localhost:9090/targets
```

## Verification Checklist

Run through this checklist after deployment:

- [ ] `curl $URL/health` returns `{"status": "ok"}`
- [ ] `curl $URL/targets` without auth returns 401/403
- [ ] `curl -H "Authorization: Bearer $ANALYST_TOKEN" $URL/targets` returns data
- [ ] `kubectl get pods -n dk-data-staging` shows all Running
- [ ] `kubectl logs job/db-init -n dk-data-staging` shows "initialization complete"
- [ ] GitHub Actions CI workflow runs on PR
- [ ] GitHub Actions CD workflow builds and pushes image on merge

## Next Steps

After successful deployment:

1. **Enable observability** (if CRDs available):
   - Uncomment ServiceMonitor in kustomization.yaml
   - Apply changes and verify metrics in Grafana

2. **Add more API views**:
   - Create views for actual data once ingestion is running
   - Update role permissions as needed

3. **Document API endpoints**:
   - Generate OpenAPI spec from PostgREST
   - Publish to API documentation portal

## GHCR Credentials Setup

For Kubernetes to pull container images from GitHub Container Registry, you need to create a Docker registry secret:

### 1. Create a GitHub Personal Access Token

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Create a new token with `read:packages` scope
3. Copy the token value

### 2. Create the Secret in Kubernetes

```bash
# Create secret for staging namespace
kubectl create secret docker-registry ghcr-credentials \
  --namespace=dk-data-staging \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_PAT \
  --docker-email=YOUR_EMAIL

# Create secret for production namespace
kubectl create secret docker-registry ghcr-credentials \
  --namespace=dk-data-prod \
  --docker-server=ghcr.io \
  --docker-username=YOUR_GITHUB_USERNAME \
  --docker-password=YOUR_GITHUB_PAT \
  --docker-email=YOUR_EMAIL
```

### 3. Verify the Secret

```bash
# Check secret exists
kubectl get secret ghcr-credentials -n dk-data-staging

# Test image pull
kubectl run test-pull --rm -it --image=ghcr.io/data-kinetic-projects/dk-data-fe/job-trigger:latest \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"ghcr-credentials"}]}}' \
  -n dk-data-staging -- echo "Pull successful"
```

The secret is referenced in:
- `k8s/base/ingestion/job-trigger-deployment.yaml`
- `k8s/base/ingestion/cronjob-*.yaml`
