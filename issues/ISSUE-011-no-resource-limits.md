# ISSUE-011: No Kubernetes Resource Limits Defined

**Project**: dk-data-FE
**Category**: Operations
**Priority**: P1 - High
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

Kubernetes deployments and CronJobs lack resource requests and limits. This can lead to:
- Pods consuming unbounded memory, causing OOMKills
- CPU starvation affecting other workloads
- Unpredictable scheduling behavior
- Cluster instability during peak loads

---

## Affected Files

| File | Component | Missing |
|------|-----------|---------|
| `.gitops/base/postgrest/deployment.yaml` | PostgREST | resources |
| `.gitops/base/ingestion/job-trigger-deployment.yaml` | Job Trigger | resources |
| `.gitops/base/ingestion/cronjob-cms-all.yaml` | CronJob | resources |
| `.gitops/base/catalog/cronjob-refresh.yaml` | CronJob | resources |

---

## Evidence from Codebase

### kustomization.yaml Resources

```yaml
resources:
  - postgrest/deployment.yaml
  - postgrest/service.yaml
  - postgrest/configmap.yaml
  - postgrest/secret.yaml
  - ingestion/cronjob-cms-all.yaml
  - catalog/cronjob-refresh.yaml
  - ingestion/job-trigger-deployment.yaml
  - ingestion/job-trigger-service.yaml
```

**Issue**: All listed resources likely lack resource specifications based on common patterns.

### docker-compose.yml - Metabase Memory

```yaml
metabase:
  environment:
    JAVA_OPTS: "-Xmx1g"
```

**Note**: Docker Compose has some memory limits, but K8s manifests don't.

---

## Risk Assessment

### Unbounded Resource Consumption

| Service | Risk | Impact |
|---------|------|--------|
| PostgREST | High memory on large queries | Node OOMKill |
| Job Trigger | Unbounded on large fetches | Node instability |
| CronJobs | Memory spike during data processing | Pod eviction |
| SQLMesh | Memory proportional to data size | Uncontrolled growth |

### Kubernetes Scheduling Impact

Without resource requests:
- Scheduler cannot make informed placement decisions
- Pods may land on overcommitted nodes
- Quality of Service (QoS) class defaults to BestEffort
- First to be evicted under memory pressure

---

## QoS Class Implications

| QoS Class | Condition | Eviction Priority |
|-----------|-----------|-------------------|
| **Guaranteed** | requests = limits (all containers) | Last evicted |
| **Burstable** | requests < limits | Middle |
| **BestEffort** | No requests or limits | First evicted |

**Current State**: All pods are BestEffort (first to be evicted)

---

## Recommended Resource Limits

### PostgREST

```yaml
# .gitops/base/postgrest/deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: postgrest
          image: postgrest/postgrest:v12.2.3
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
```

**Rationale**:
- PostgREST is lightweight, mainly passes queries to PostgreSQL
- Memory spikes on large result sets
- `PGRST_MAX_ROWS: 1000` limits response size

### Job Trigger Service

```yaml
# .gitops/base/ingestion/job-trigger-deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: job-trigger
          image: tavr-job-trigger:latest
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
```

**Rationale**:
- FastAPI is memory-efficient for API handling
- CPU spikes during job orchestration
- Needs headroom for spawning subprocesses (local mode)

### CMS Fetch CronJob

```yaml
# .gitops/base/ingestion/cronjob-cms-all.yaml
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: fetch-cms
              image: tavr-job-trigger:latest
              resources:
                requests:
                  cpu: "500m"
                  memory: "512Mi"
                limits:
                  cpu: "2000m"
                  memory: "4Gi"
```

**Rationale**:
- CMS data files can be 100MB+ CSV files
- Pandas reads entire file into memory
- CPU needed for data validation
- Peak memory: ~3x file size for parsing

### Catalog Refresh CronJob

```yaml
# .gitops/base/catalog/cronjob-refresh.yaml
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: catalog-refresh
              image: tavr-job-trigger:latest
              resources:
                requests:
                  cpu: "100m"
                  memory: "128Mi"
                limits:
                  cpu: "500m"
                  memory: "256Mi"
```

**Rationale**:
- Lightweight metadata queries
- No large data processing
- Quick execution (~30 seconds)

### SQLMesh CronJob

```yaml
# .gitops/base/sqlmesh/cronjob.yaml (if exists)
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: sqlmesh
              image: tavr-sqlmesh:latest
              resources:
                requests:
                  cpu: "500m"
                  memory: "1Gi"
                limits:
                  cpu: "4000m"
                  memory: "8Gi"
```

**Rationale**:
- SQLMesh processes entire tables
- Memory proportional to dataset size
- CPU-intensive transformation queries

---

## Resource Sizing Guidelines

### Calculation Method

```
Memory Limit = (Peak Memory * 1.5) + Container Overhead

Where:
- Peak Memory = Maximum observed memory during load testing
- 1.5 = Safety factor for variance
- Container Overhead = ~50-100Mi for Python runtime
```

### Monitoring for Tuning

```bash
# Get current resource usage
kubectl top pods -n tavr-data

# Get historical resource usage
kubectl describe pod <pod-name> -n tavr-data | grep -A 5 "Limits"

# Check for OOMKills
kubectl get events -n tavr-data --field-selector=reason=OOMKilled
```

---

## Implementation

### LimitRange for Namespace Defaults

```yaml
# .gitops/base/limitrange.yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: tavr-limits
  namespace: tavr-data
spec:
  limits:
    - type: Container
      default:
        cpu: "500m"
        memory: "512Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      min:
        cpu: "50m"
        memory: "64Mi"
      max:
        cpu: "4000m"
        memory: "8Gi"
```

### ResourceQuota for Namespace

```yaml
# .gitops/base/resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tavr-quota
  namespace: tavr-data
spec:
  hard:
    requests.cpu: "8"
    requests.memory: "16Gi"
    limits.cpu: "16"
    limits.memory: "32Gi"
    pods: "20"
```

---

## Kustomize Patches

### Environment-Specific Overrides

```yaml
# .gitops/overlays/prod/patches/resources.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgrest
spec:
  template:
    spec:
      containers:
        - name: postgrest
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: job-trigger
spec:
  template:
    spec:
      containers:
        - name: job-trigger
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
```

```yaml
# .gitops/overlays/prod/kustomization.yaml
resources:
  - ../../base

patches:
  - path: patches/resources.yaml
```

---

## Vertical Pod Autoscaler (Optional)

```yaml
# .gitops/base/vpa/postgrest-vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: postgrest-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: postgrest
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
      - containerName: postgrest
        minAllowed:
          cpu: "50m"
          memory: "64Mi"
        maxAllowed:
          cpu: "2000m"
          memory: "2Gi"
```

---

## Implementation Checklist

- [ ] Add resources to postgrest deployment
- [ ] Add resources to job-trigger deployment
- [ ] Add resources to all CronJob templates
- [ ] Create LimitRange for namespace defaults
- [ ] Create ResourceQuota for namespace
- [ ] Add environment-specific patches in overlays
- [ ] Test resource limits don't cause OOMKills
- [ ] Set up monitoring for resource usage
- [ ] Document resource sizing rationale
- [ ] Consider VPA for dynamic sizing

---

## Testing Resource Limits

```bash
# Simulate load to test limits
kubectl run load-test --image=busybox --rm -it -- sh -c "
  while true; do
    wget -q -O /dev/null http://postgrest:3000/targets?limit=1000
    sleep 0.1
  done
"

# Watch resource usage
watch kubectl top pods -n tavr-data

# Check for throttling
kubectl describe pod postgrest-xxx -n tavr-data | grep -i throttl
```

---

## References

- [Kubernetes: Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes: QoS Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
- [Kubernetes: LimitRange](https://kubernetes.io/docs/concepts/policy/limit-range/)
- [Kubernetes: ResourceQuota](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
