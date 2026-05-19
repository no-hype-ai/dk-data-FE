# Quickstart: Observability Dashboard & Metrics Fix

## Prerequisites

- VPN connected (`scutil --nc status "Nick"` → Connected)
- SSH tunnel to k3s cluster (`ssh -L 50005:10.0.0.11:6443 root@192.168.10.8 -N &`)
- Fresh kubeconfig (`export KUBECONFIG=/tmp/k3s-fresh.yaml`)
- Python 3.11+ with project dependencies (`cd src && pip install -e .`)

## Development Workflow

### Phase A: Dashboard query fixes (no code, Grafana UI only)

```bash
# Port-forward Grafana
kubectl port-forward -n infra svc/grafana 3000:3000 &

# Get admin password
GRAFANA_PW=$(kubectl get secret grafana-secret -n infra -o jsonpath='{.data.GRAFANA_ADMIN_PASSWORD}' | base64 -d)

# Open Grafana at http://localhost:3000 (admin / $GRAFANA_PW)
# Fix queries directly in each dashboard's panel editor
```

### Phase B: Metrics instrumentation (code changes)

```bash
# Key files to modify:
# 1. Extend DB refresh function
vim src/dk_data/services/data_platform/metrics.py
# → Add queries to refresh_metrics_from_database_sync()

# 2. Wire CronJob metric recording
vim src/dk_data/ingestion/main.py
# → Add meta.batch_job_runs INSERT on completion

# 3. Add HTTP instrumentation
vim src/dk_data/ingestion/batch/api.py
# → Add prometheus-fastapi-instrumentator

# Run tests
cd src && pytest tests/ -v

# Build and deploy to staging
# (follow existing CI/CD pipeline)
```

### Phase C: Monitoring restructure

```bash
# Rename directories
git mv monitoring/dashboards grafana/dashboards
git mv monitoring/alerts grafana/alerts
rm -rf monitoring/provisioning monitoring/

# Delete K8s CRDs
rm k8s/apps/infrastructure/base/alert-rules.yaml
rm k8s/apps/infrastructure/base/recording-rules.yaml
rm k8s/apps/infrastructure/base/service-monitor.yaml
rm k8s/apps/metering-proxy/base/servicemonitor.yaml

# Update kustomizations (edit to remove deleted file references)
```

## Verification Commands

```bash
# Check metrics in Mimir
kubectl port-forward -n infra svc/mimir 8080:8080 &

# Count dk_* metrics with data
curl -s 'http://localhost:8080/prometheus/api/v1/label/__name__/values' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(len([n for n in d['data'] if n.startswith('dk_')]))"

# Check specific metric
curl -s --data-urlencode 'query=dk_layer_record_count' 'http://localhost:8080/prometheus/api/v1/query'

# Check recording rules
curl -s 'http://localhost:8080/prometheus/api/v1/rules' | python3 -m json.tool

# Check Alloy for out-of-order errors
kubectl logs -n infra daemonset/alloy --tail=100 | grep -c "out-of-order"

# Validate kustomize (no CRDs)
kubectl kustomize k8s/base/ | grep -c "monitoring.coreos.com"  # should be 0
```

## Key File Locations

| Purpose | Path |
|---------|------|
| Metric definitions (75 metrics) | `src/dk_data/observability/metrics.py` |
| DB refresh function | `src/dk_data/services/data_platform/metrics.py` |
| `/metrics` endpoint | `src/dk_data/ingestion/batch/api.py:264` |
| CronJob entry point | `src/dk_data/ingestion/main.py` |
| Job runner (API-triggered) | `src/dk_data/ingestion/batch/job_runner.py` |
| Dashboard JSONs | `monitoring/dashboards/` → `grafana/dashboards/` |
| Alert YAMLs | `monitoring/alerts/` → `grafana/alerts/` |
| K8s CRDs (to delete) | `k8s/apps/infrastructure/base/` |
