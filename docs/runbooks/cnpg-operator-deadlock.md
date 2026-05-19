# Runbook: CNPG operator deadlock (DiskPressure / selfHeal reconcile loop)

**Incident reference**: 2026-04-15 (session memory obs 2541–2543), dk-alchemy issue #637
**Last verified**: 2026-04-15
**Severity**: Critical — all Postgres writes are blocked while this is in effect.
**Audience**: on-call platform engineer.

## Why this runbook exists

On 2026-04-15 the dk-data-FE prestaged hydration Job filled `/var/lib/containerd` on `k3s-master-1` (penguin). The node flipped to `DiskPressure: True`, which evicted every Pod on it — **including the CNPG operator**. ArgoCD's `selfHeal` then re-created the operator Pod, which the scheduler (matching the existing affinity rule) placed right back onto the tainted node, where it was immediately evicted again. Lather, rinse, repeat. While this reconcile loop ran:

- The `Cluster` CR for `postgres-cluster` stayed stuck in `Recovering`.
- The RW Service's `Endpoints` object was empty.
- Every dk-data-FE writer — hydration, SQLMesh, web-anon writes — saw `server closed the connection unexpectedly` / `no connection to the server`.

The fix is **not** to carve an exception into ArgoCD `selfHeal`. The fix is to get the node out of `DiskPressure` so ArgoCD's next reconcile lands the operator on a healthy node. If you are here because it happened again, work top-to-bottom.

Prevention for this class of incident lives in plan.md §B.1 (node anti-affinity via `dk.role=general`) and §B.10 (node labels + `priorityClassName`). The structural fix is in dk-alchemy issue [#649](https://github.com/data-kinetic/dk-alchemy/issues/649) (dk-data postgres migration to `local-path-db-large`).

---

## Detection

Any **one** of the following signatures confirms you are in this failure mode.

### 1. CNPG operator Pods are not Ready

```bash
kubectl -n cnpg-system get pods
```

**Failure-mode output** (0/1 Ready, high restart count, recent age):

```
NAME                                        READY   STATUS    RESTARTS     AGE
cnpg-cloudnative-pg-5f7d8c9b6d-abcde        0/1     Evicted   0            2m
cnpg-cloudnative-pg-5f7d8c9b6d-fghij        0/1     Pending   0            45s
```

### 2. Cluster CR stuck in `Creating` or `Recovering`

```bash
kubectl -n infra get cluster postgres-cluster -o jsonpath='{.status.phase}{"\n"}'
```

**Failure-mode output**:

```
Recovering
```

or

```
Creating
```

(Healthy reads `Cluster in healthy state`.)

### 3. RW Service endpoint list is empty

```bash
kubectl -n infra get endpoints postgres-cluster-rw
```

**Failure-mode output**:

```
NAME                  ENDPOINTS   AGE
postgres-cluster-rw   <none>      37d
```

(Healthy shows one IP:5432 pair.)

### 4. All writes fail with the same connection error

Application logs (platform-api, PostgREST, hydration Jobs) burst with:

```
psycopg2.OperationalError: server closed the connection unexpectedly
	This probably means the server terminated abnormally
	before or while processing the request.
```

or

```
FATAL: no connection to the server
```

If you see **any two** of the above, continue.

---

## Triage

Find which node is under disk pressure.

### 1. Scan every node's conditions

```bash
for node in $(kubectl get nodes -o name); do
  echo "=== $node ==="
  kubectl describe $node | grep -A1 'DiskPressure\|MemoryPressure\|PIDPressure'
done
```

**Failure-mode output** (the tainted node will show `DiskPressure: True`):

```
=== node/penguin ===
  DiskPressure     True    Thu, 15 Apr 2026 14:22:03 -0700   ...   KubeletHasDiskPressure   kubelet has disk pressure
=== node/krang ===
  DiskPressure     False   ...
=== node/scarecrow ===
  DiskPressure     False   ...
```

### 2. Confirm ArgoCD selfHeal is actively reconciling the operator back onto the tainted node

```bash
kubectl -n cnpg-system get events --sort-by=.lastTimestamp | tail -20
```

**Failure-mode output** (alternating `Scheduled` → `Evicted` on the same node):

```
2m   Normal   Scheduled   pod/cnpg-cloudnative-pg-5f7d8c9b6d-abcde   Successfully assigned cnpg-system/... to penguin
2m   Warning  Evicted     pod/cnpg-cloudnative-pg-5f7d8c9b6d-abcde   The node was low on resource: ephemeral-storage.
90s  Normal   Scheduled   pod/cnpg-cloudnative-pg-5f7d8c9b6d-fghij   Successfully assigned cnpg-system/... to penguin
```

If you see the same node in the `Scheduled` target repeatedly, ArgoCD `selfHeal` is fighting you. **Do not disable selfHeal.** Take the node out of the scheduling pool instead (next section).

**Time budget for this section**: ≤ 2 minutes.

---

## Emergency unblock path (no ArgoCD edits)

Do these in order. The first three are enough in ~95% of cases; steps 4 and 5 are last resort.

### Step 1 — Free disk on the tainted node

SSH to the tainted node (or `kubectl debug node/<name>`) and reclaim space. In priority order:

```bash
# On the tainted node:

# 1. Containerd's temporary image-pull mounts — always safe to delete
sudo rm -rf /var/lib/containerd/tmpmounts/*

# 2. Evicted pod volumes — already orphaned
sudo find /var/lib/kubelet/pods -maxdepth 2 -type d -name 'volumes' | \
  xargs -I{} sudo du -sh {} 2>/dev/null | sort -h | tail -10
# inspect, then delete the pod directories whose Pod no longer exists in kubectl get pods -A

# 3. Prestaged hydration dumps already mirrored to SeaweedFS
# (Safe to delete — run `dk data hydrate status` to confirm s3://dk-data-prestaged/<run-label>/ has the artifact)
sudo rm -rf "${PRESTAGED_ROOT:-/var/lib/dk-data/prestaged}"/*.dump

# 4. Container image layers for images no longer referenced by a running Pod
sudo crictl rmi --prune
```

**Verify pressure cleared**:

```bash
kubectl describe node <tainted-node> | grep DiskPressure
# Expected: DiskPressure     False
```

**Time budget**: 3–5 minutes.

### Step 2 — Cordon the tainted node to stop new Pods landing

Even after disk is freed, the kubelet may take 30–60 seconds to drop the `DiskPressure` condition. Cordon the node so the scheduler stops targeting it during that window:

```bash
kubectl cordon <tainted-node>
```

**Expected output**:

```
node/<tainted-node> cordoned
```

**Time budget**: < 10 seconds.

### Step 3 — Wait for ArgoCD to reconcile the operator onto a healthy node

ArgoCD runs a reconciliation loop every ~3 minutes. Force a sync to avoid waiting:

```bash
argocd app sync infra-cnpg-operator
```

(Or wait up to 3 minutes.)

Then watch Pods come Ready:

```bash
kubectl -n cnpg-system get pods -w
```

**Expected progression**:

```
NAME                                        READY   STATUS              RESTARTS   AGE
cnpg-cloudnative-pg-5f7d8c9b6d-klmno        0/1     ContainerCreating   0          5s
cnpg-cloudnative-pg-5f7d8c9b6d-klmno        0/1     Running             0          18s
cnpg-cloudnative-pg-5f7d8c9b6d-klmno        1/1     Running             0          30s
```

Confirm the Cluster CR recovers:

```bash
kubectl -n infra get cluster postgres-cluster -o jsonpath='{.status.phase}{"\n"}'
# Expected: Cluster in healthy state

kubectl -n infra get endpoints postgres-cluster-rw
# Expected: one IP:5432 pair
```

**Time budget**: 1–3 minutes.

### Step 4 — Uncordon the tainted node once the primary is back up

```bash
kubectl uncordon <tainted-node>
```

**Expected output**:

```
node/<tainted-node> uncordoned
```

**Do not skip this step** — a forever-cordoned node eventually breaks capacity planning and other reconcile loops.

**Time budget**: < 10 seconds.

### Step 5 — Last resort: manual replica promotion

Only if steps 1–4 cannot restore a primary within 15 minutes (e.g., you cannot free disk and no healthy node has capacity). This bypasses CNPG; you are trading safety for availability and **must** follow up with a postmortem.

```bash
# 1. Find a healthy replica
kubectl -n infra get pods -l cnpg.io/cluster=postgres-cluster -o wide

# 2. Promote it manually
kubectl exec -n infra <replica-pod> -- psql -U postgres -c "SELECT pg_promote();"
# Expected: pg_promote returns t

# 3. Manually repoint the RW Service endpoint at the promoted replica's IP
kubectl -n infra get pod <replica-pod> -o jsonpath='{.status.podIP}{"\n"}'

# 4. Patch the Endpoints object to point writers at it
kubectl -n infra patch endpoints postgres-cluster-rw --type=json \
  -p='[{"op":"replace","path":"/subsets/0/addresses","value":[{"ip":"<replica-ip>","nodeName":"<node>"}]}]'
```

**Warning**: CNPG's reconciler will eventually overwrite the Endpoints patch when the operator is healthy again. Plan to re-converge immediately after steps 1–4 succeed. Open a dk-alchemy issue documenting the split-brain risk window.

**Time budget**: 5–10 minutes. Escalate to the dk-alchemy on-call before running step 5.

---

## Postmortem

Within 24 hours of the incident:

### 1. Capture the lesson

Use the `lessons-learned` skill to add an entry to `.dk/memory/lessons.md`. Minimum content:

- Which node flipped to `DiskPressure` and what filled the disk
- Which reconcile signature you observed (selfHeal vs. operator restart loop vs. other)
- Time-to-detection and time-to-recovery
- Whether step 5 (manual promotion) was needed
- Which prevention item in plan.md §B.1 / §B.10 would have prevented it

### 2. File a dk-alchemy issue on the underlying disk failure

```bash
gh issue create --repo data-kinetic/dk-alchemy \
  --title "disk: <node> hit DiskPressure on <date> — <root cause>" \
  --label "area:infra,area:storage,scope:incident" \
  --body "Reference: dk-data-FE <runbook invocation timestamp>.
Root cause: <what filled the disk>.
Remediation applied: <link to this runbook section>.
Structural fix requested: <e.g., accelerate dk-alchemy #649>."
```

This is the feedback loop that gets the cluster-level fix prioritized. Do not skip it — a silent recovery means this will happen again.

---

## Prevention

This runbook is an edge-case tool. The structural fixes live elsewhere:

- **plan.md §B.1** — hydration Jobs get `nodeAffinity: dk.role In (general)`, ephemeral-storage `requests`/`limits`, and no toleration for `node.kubernetes.io/disk-pressure`. That alone prevents the hydration-caused variant of this incident.
- **plan.md §B.10** — verify `dk.role`, `dk.storage`, and `topology.kubernetes.io/zone` labels are present on every node so the affinity rule actually binds. CNPG operator gets `priorityClassName: production-critical` so if the scheduler must choose, it evicts something else.
- **dk-alchemy issue [#649](https://github.com/data-kinetic/dk-alchemy/issues/649)** — migrates dk-data postgres to the dedicated `local-path-db-large` storage class on a dedicated node. Removes the co-tenancy that makes dk-data-FE's disk usage an availability risk for CNPG.
- **dk-alchemy issue [#637](https://github.com/data-kinetic/dk-alchemy/issues/637)** — tracks the original 2026-04-15 operator-deadlock incident and the ArgoCD `selfHeal` reconcile-loop behavior that this runbook works around.
- **dk-alchemy issue [#651](https://github.com/data-kinetic/dk-alchemy/issues/651)** — retroactive node label application so the §B.10 affinity rules bind on every node.

When every item above has landed, this runbook should fire once per year or less. If you invoke it more than twice per quarter, escalate the structural work — the operational glue is not the fix.

---

## Appendix: command quickref

Copy-paste card for when the cluster is on fire. Every command is idempotent; each time budget is p95 on a healthy control plane.

| # | Command | Purpose | Expected output | Budget |
|---|---------|---------|-----------------|-------:|
| 1 | `kubectl -n cnpg-system get pods` | Confirm operator unhealthy | 0/1 Ready or Evicted | 5s |
| 2 | `kubectl -n infra get cluster postgres-cluster -o jsonpath='{.status.phase}{"\n"}'` | Confirm Cluster CR state | `Recovering` or `Creating` | 5s |
| 3 | `kubectl -n infra get endpoints postgres-cluster-rw` | Confirm no primary | `<none>` | 5s |
| 4 | `for n in $(kubectl get nodes -o name); do echo $n; kubectl describe $n \| grep DiskPressure; done` | Find tainted node | one `True` | 20s |
| 5 | `kubectl -n cnpg-system get events --sort-by=.lastTimestamp \| tail -20` | Confirm selfHeal loop | alternating Scheduled/Evicted | 5s |
| 6 | `sudo rm -rf /var/lib/containerd/tmpmounts/*` (on tainted node) | Reclaim tmpmounts | silent success | 30s |
| 7 | `sudo rm -rf "${PRESTAGED_ROOT:-/var/lib/dk-data/prestaged}"/*.dump` (on tainted node) | Reclaim dump artifacts (already on SeaweedFS) | silent success | 30s |
| 8 | `sudo crictl rmi --prune` (on tainted node) | Reclaim image layers | `Removed image …` lines | 60s |
| 9 | `kubectl describe node <tainted-node> \| grep DiskPressure` | Confirm pressure cleared | `DiskPressure     False` | 5s |
| 10 | `kubectl cordon <tainted-node>` | Stop new Pods landing | `node/… cordoned` | 5s |
| 11 | `argocd app sync infra-cnpg-operator` | Force ArgoCD reconcile | `Sync status: Synced` | 30s |
| 12 | `kubectl -n cnpg-system get pods -w` | Watch operator become Ready | `1/1 Running` | 90s |
| 13 | `kubectl -n infra get cluster postgres-cluster -o jsonpath='{.status.phase}{"\n"}'` | Confirm primary recovered | `Cluster in healthy state` | 5s |
| 14 | `kubectl -n infra get endpoints postgres-cluster-rw` | Confirm RW endpoint populated | one `IP:5432` pair | 5s |
| 15 | `kubectl uncordon <tainted-node>` | Return node to scheduling pool | `node/… uncordoned` | 5s |
| 16 | `gh issue create --repo data-kinetic/dk-alchemy …` | Feedback loop on underlying disk failure | issue URL | 60s |

**Total budgeted unblock time (steps 1–15): ≤ 10 minutes** on a healthy cluster where disk is simply full. Longer if step 5 (manual promotion) is required or if disk reclamation requires deeper investigation.
