# Node Role Isolation

**Purpose**: explain how dk-data workloads are kept off the control plane through a combined label + taint model, and give operators the commands they need to verify, extend, and debug that model.

**Status**: runbook for the structural isolation introduced in `plan.md` §D.4 (Horizon 3: Scale-ready). Coordination tracked in [dk-alchemy #660](https://github.com/data-kinetic/dk-alchemy/issues/660).

---

## 1. Why this exists

On 2026-04-15 a dk-data-FE hydration Job ran on `k3s-master-1` (penguin), filled the node's ephemeral storage, caused `DiskPressure`, and evicted the CNPG operator — taking the Postgres write path down for every tenant (dk-alchemy #637). The Job had correct `nodeAffinity` intent (`dk.role In (general)`) but at scheduling time the `dk.role` label had not yet been applied to penguin, so the affinity rule matched every node including the control plane.

Labels alone are a **preference** signal. A missing or mutated label silently disables the constraint. To make this incident class *structurally impossible*, dk-alchemy applies a **taint** on the control-plane / data-platform nodes. A Pod without the matching toleration cannot schedule there regardless of what the labels say.

---

## 2. Node role taxonomy (canonical: dk-alchemy §2)

Every node carries the following labels:

| Label | Values | Meaning |
|-------|--------|---------|
| `dk.role` | `control` \| `general` \| `bulk` | What class of workload this node is *for* |
| `dk.storage` | `nvme-hdd` \| `hdd` | What storage profile the node offers |
| `topology.kubernetes.io/zone` | `penguin` \| `krang` \| `scarecrow` | Physical host (for anti-affinity) |

Current node assignments:

| Node | `dk.role` | `dk.storage` | Zone |
|------|-----------|--------------|------|
| `k3s-master-1` (penguin) | `control` | `nvme-hdd` | `penguin` |
| `k3s-slave-1` (krang) | `general` | `nvme-hdd` | `krang` |
| `k3s-slave-2` (scarecrow, joining) | `bulk` | `hdd` | `scarecrow` |

Canonical source: [`dk-alchemy-2-overview.md` §2](https://github.com/data-kinetic/dk-alchemy/blob/main/dk-alchemy-2-overview.md#2-cluster-topology-and-scheduling-contracts).

### Why the label alone is not enough

The label is consumed by pod `nodeAffinity` / `nodeSelector` — but:
- If the label is missing at scheduling time (rollout race), the constraint silently matches everything.
- If a misconfigured workload omits the affinity rule entirely, nothing stops it from landing on a control-plane node.
- If an emergency hotfix relaxes the affinity, there is no second line of defense.

---

## 3. Taint model (D.4)

Alongside the labels, control-plane / data-platform nodes carry a `NoSchedule` taint:

```
node.datakinetic.com/role=control-plane:NoSchedule
```

Coverage (as of dk-alchemy #660):

| Node | Tainted? | Reason |
|------|----------|--------|
| `k3s-master-1` (penguin) | **Yes** | control-plane + CNPG + ArgoCD + observability |
| `k3s-slave-1` (krang) | No | dk-data-FE's hydration target (`dk.role=general`) |
| `k3s-slave-2` (scarecrow) | Yes, once Loki/Mimir/Tempo migrate onto it | bulk observability host |

**Only** pods that explicitly tolerate this taint can schedule on a tainted node. dk-data-FE's `prestaged-hydrate` Job intentionally does **not** tolerate it — so even if the `dk.role=general` affinity rule failed open, the Job still could not land on penguin.

Orthogonal existing taints:
- `k3s-slave-1` (krang): `nvidia.com/gpu=true:NoSchedule` — GPU isolation (unrelated key).

---

## 4. Verification commands

All commands are read-only or produce Pending pods; none mutate cluster state.

### 4a. Confirm the taint is applied

```bash
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
TAINTS:.spec.taints[*].key,\
EFFECT:.spec.taints[*].effect,\
ROLE:.metadata.labels.dk\\.role
```

Expected on a healthy cluster (post dk-alchemy #660):

```
NAME           TAINTS                                                  EFFECT                    ROLE
k3s-master-1   node.datakinetic.com/role                               NoSchedule                control
k3s-slave-1    nvidia.com/gpu                                          NoSchedule                general
k3s-slave-2    node.datakinetic.com/role                               NoSchedule                bulk
```

Per-node detail:

```bash
kubectl describe node k3s-master-1 | grep -E '^(Name:|Taints:|Labels:)'
```

### 4b. Scheduler dry-run — proves a tolerations-less Pod stays Pending

Apply this manifest, wait 60 seconds, read the event, then delete it. It **must** remain `Pending`.

```yaml
# taint-verify-no-tol.yaml
apiVersion: v1
kind: Pod
metadata:
  name: taint-verify-no-tol
  namespace: default
spec:
  nodeSelector:
    kubernetes.io/hostname: k3s-master-1
  restartPolicy: Never
  containers:
    - name: pause
      image: registry.k8s.io/pause:3.9
```

```bash
kubectl apply -f taint-verify-no-tol.yaml
sleep 60
kubectl describe pod taint-verify-no-tol | grep -A5 Events:
kubectl delete pod taint-verify-no-tol --wait=false
```

Expected event:

```
FailedScheduling ... 0/3 nodes are available: 1 node(s) had untolerated taint
{node.datakinetic.com/role: control-plane}, 2 node(s) didn't match Pod's
node affinity/selector.
```

If the Pod schedules instead, the taint is missing or mis-configured — escalate to dk-alchemy owners.

### 4c. Confirm the hydrate Job is still schedulable

```bash
# Dry-run the scheduler against the real Job manifest.
kubectl --dry-run=server apply -f deploy/jobs/prestaged-hydrate.yaml
kubectl get pods -n dk-data-prod -l app=prestaged-hydrate -o wide
```

The pod must land on a `dk.role=general` node (today: `k3s-slave-1`). It must **not** land on any tainted node.

---

## 5. How to add a new node role

Suppose we add a GPU inference pool on a new node:

1. **Propose the taxonomy extension** in dk-alchemy §2 (opens a PR against `dk-alchemy-2-overview.md`).
2. **Extend the label set**: e.g. `dk.role=gpu-inference`, `dk.storage=nvme-hdd`.
3. **Decide on a taint**: if the pool is dedicated (only GPU pods may run there), add `node.datakinetic.com/role=gpu-inference:NoSchedule`. If it is general compute that merely prefers inference workloads, skip the taint and rely on weighted `preferredDuringScheduling` affinity.
4. **Update every consumer** that must tolerate the new taint — search for `tolerations:` blocks and add the new key. **Do not** broaden existing tolerations to a wildcard.
5. **Update this runbook** section 2 (taxonomy table) and section 3 (taint coverage table).
6. **Run the verification procedure** in section 4b against the new node using a tolerations-less dummy Pod.

### Never do this

- ❌ `kubectl taint` by hand on a node — always via ArgoCD drift-repair against dk-alchemy manifests. Direct kubectl writes are flagged by the `warn-non-argocd-writes` Kyverno policy (dk-alchemy §10).
- ❌ A wildcard toleration (`operator: Exists` with no `key`) — it defeats the taint model entirely.
- ❌ Adding a toleration to "unblock" a scheduling error in prod. If a pod needs to run on a tainted node, the pod's *role* is wrong, not its tolerations.

---

## 6. Kyverno PolicyException

The hydrate Job does not need an exception to schedule today — its `dk.role=general` affinity plus its lack of the control-plane toleration means it simply never lands on a tainted node.

A placeholder PolicyException ships at `k8s/apps/security/policy-exceptions/hydrate-taint-exception.yaml` in `validationFailureAction: Audit` mode. It becomes operative only if dk-alchemy enforces a future `require-role-toleration` ClusterPolicy — at which point this runbook and the exception should be re-reviewed together.

---

## 7. References

- dk-alchemy `dk-alchemy-2-overview.md` §2 — canonical node taxonomy
- dk-alchemy `dk-alchemy-2-overview.md` §10 — Kyverno enforcement roadmap
- [dk-alchemy #660](https://github.com/data-kinetic/dk-alchemy/issues/660) — apply the taint (this PR's coordination issue)
- dk-alchemy #651 (closed) — `dk.role` label rollout (prerequisite)
- dk-alchemy #637 (closed) — the 2026-04-15 DiskPressure / CNPG eviction incident this runbook exists to prevent
- dk-data-FE `plan.md` §D.4 — Horizon 3: Scale-ready rationale
