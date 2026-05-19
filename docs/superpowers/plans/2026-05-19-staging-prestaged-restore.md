# Staging Prestaged Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one staging-only `staging-prestaged-restore` CronJob that `pg_restore`s prod's existing `pg-backup-daily` artifact into staging's `dk_data`, so WS4 SP3's `^fetch-*` suspension does not stale staging data.

**Architecture:** Approach A — reuse prod's already-once-created daily dump. No producer, no per-source tree, no S3→PVC sync. A staging-overlay-only manifest (PVC + ConfigMap script + DopplerSecret + CronJob) downloads the latest `postgres-backups/dk-data-prod/daily/*.dump` from prod's SeaweedFS, verifies it, restores in-place into the separate staging Postgres, and writes a `meta.transform_runs` breadcrumb. Observability is a hand-applied `PrometheusRule` on `kube_job_status_failed` plus a small Grafana dashboard. Reversible by deleting one overlay resource line.

**Tech Stack:** Kubernetes (Kustomize overlays), `pg_restore`/`psql` (`ghcr.io/cloudnative-pg/postgresql:16.4`), MinIO client `mc` (init container), Doppler operator (`secrets.doppler.com/v1alpha1`), Prometheus Operator CRD (`monitoring.coreos.com/v1`), pytest + PyYAML for offline manifest assertions.

**Spec:** `docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `k8s/overlays/staging/staging-prestaged-restore.yaml` (create) | 4 docs: scratch `PersistentVolumeClaim`, `ConfigMap` (restore.sh), `DopplerSecret` (prod-store read creds), `CronJob`. Staging-overlay-only — never in `base/` or `prod/`. |
| `k8s/overlays/staging/kustomization.yaml` (modify) | Add the new file to `resources:`. |
| `grafana/alerts/staging-prestaged-restore.yaml` (create) | Orphaned `PrometheusRule` (hand-applied, mirrors `grafana/alerts/gold-zero-rows.yaml` convention) alerting on restore-job failure + staleness. |
| `grafana/dashboards/applications/dk-data-fe-staging-prestaged-restore.json` (create) | Small dashboard: last restore status from `meta.transform_runs` + `kube_job_status_failed`. |
| `docs/runbooks/staging-prestaged-restore.md` (create) | Operator precondition checklist + manual-trigger + rollback. |
| `tests/infra/test_staging_prestaged_restore.py` (create) | Offline assertions: manifest shape, script contracts, bash syntax, DopplerSecret config, overlay-only wiring, kubectl-guarded render, alert + dashboard shape. |

The repo applies `namespace`/`labels` from the overlay to every resource, so the manifest **must not** hardcode `namespace` (matches `pg-backup-daily.yaml`).

---

## Task 1: Manifest skeleton — PVC + DopplerSecret + CronJob (no script yet)

**Files:**
- Create: `k8s/overlays/staging/staging-prestaged-restore.yaml`
- Test: `tests/infra/test_staging_prestaged_restore.py`

- [ ] **Step 1: Write the failing test**

Create `tests/infra/test_staging_prestaged_restore.py`:

```python
"""Offline contract guard for the staging-prestaged-restore pipeline.

Approach A (spec: docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md):
staging consumes prod's existing pg-backup-daily artifact instead of
re-fetching. These assertions pin the manifest + script contract so it
cannot silently regress (wrong store, wrong DB, fetcher-name collision
with SP3's ^fetch-* suspension, lost integrity gate).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "k8s" / "overlays" / "staging" / "staging-prestaged-restore.yaml"
STAGING_KUSTOMIZATION = REPO_ROOT / "k8s" / "overlays" / "staging" / "kustomization.yaml"
PROD_KUSTOMIZATION = REPO_ROOT / "k8s" / "overlays" / "prod" / "kustomization.yaml"


@pytest.fixture(scope="module")
def docs() -> dict:
    raw = list(yaml.safe_load_all(MANIFEST.read_text()))
    return {d["kind"]: d for d in raw if d}


def test_manifest_has_the_four_kinds(docs):
    assert set(docs) == {
        "PersistentVolumeClaim",
        "ConfigMap",
        "DopplerSecret",
        "CronJob",
    }, f"unexpected kinds: {sorted(docs)}"


def test_cronjob_contract(docs):
    cj = docs["CronJob"]
    assert cj["metadata"]["name"] == "staging-prestaged-restore"
    spec = cj["spec"]
    assert spec["schedule"] == "0 2 * * *"
    assert spec["concurrencyPolicy"] == "Forbid"
    job = spec["jobTemplate"]["spec"]
    assert job["backoffLimit"] == 1
    assert job["activeDeadlineSeconds"] == 21600
    pod = job["template"]["spec"]
    assert pod["restartPolicy"] == "Never"
    ctr = pod["containers"][0]
    assert ctr["image"] == "ghcr.io/cloudnative-pg/postgresql:16.4"
    assert ctr["command"] == ["/bin/bash", "/scripts/restore.sh"]
    claims = [
        v["persistentVolumeClaim"]["claimName"]
        for v in pod["volumes"]
        if "persistentVolumeClaim" in v
    ]
    assert "staging-restore-scratch" in claims


def test_cronjob_name_is_not_a_fetcher(docs):
    # SP3 suspends every CronJob whose name matches ^fetch-.* . This job
    # MUST stay running, so its name must not match that regex.
    name = docs["CronJob"]["metadata"]["name"]
    assert not re.match(r"^fetch-.*", name), (
        f"{name} would be suspended by SP3's ^fetch-* target"
    )


def test_scratch_pvc_sized_for_daily_dump(docs):
    pvc = docs["PersistentVolumeClaim"]
    assert pvc["metadata"]["name"] == "staging-restore-scratch"
    req = pvc["spec"]["resources"]["requests"]["storage"]
    assert req == "250Gi"


def test_dopplersecret_reads_prod_store_creds(docs):
    ds = docs["DopplerSecret"]
    assert ds["metadata"]["name"] == "dk-data-prestaged-src-credentials"
    # config must be 'prd' (prod-store read creds). The staging overlay's
    # DopplerSecret patches target other names, never this one, so it
    # stays prd even under the staging overlay.
    assert ds["spec"]["config"] == "prd"
    assert ds["spec"]["managedSecret"]["name"] == "dk-data-prestaged-src-credentials"


def test_manifest_has_no_hardcoded_namespace(docs):
    # Kustomize sets namespace from the overlay; hardcoding it would
    # leak the job into the wrong namespace if the file is ever reused.
    for kind, d in docs.items():
        assert "namespace" not in d["metadata"], (
            f"{kind} must not hardcode metadata.namespace"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v`
Expected: FAIL — `FileNotFoundError` for `staging-prestaged-restore.yaml`.

- [ ] **Step 3: Write the manifest (skeleton — placeholder script body, real everything else)**

Create `k8s/overlays/staging/staging-prestaged-restore.yaml`:

```yaml
# WS4 SP3 follow-on (feature 211) — staging prestaged restore.
# Spec: docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md
#
# Staging-overlay-ONLY. Reuses prod's existing pg-backup-daily artifact
# (postgres-backups/dk-data-prod/daily/*.dump) so external sources are
# fetched once (prod) not twice. Name is deliberately NOT ^fetch-* so
# SP3's suspension target leaves it running. Kustomize owns namespace +
# labels — do not hardcode metadata.namespace here.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: staging-restore-scratch
  labels:
    app: staging-prestaged-restore
    app.kubernetes.io/part-of: dk-data
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 250Gi
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: staging-prestaged-restore-script
  labels:
    app: staging-prestaged-restore
    app.kubernetes.io/part-of: dk-data
data:
  restore.sh: |
    #!/bin/bash
    echo "placeholder - replaced in Task 2"
    exit 1
---
apiVersion: secrets.doppler.com/v1alpha1
kind: DopplerSecret
metadata:
  name: dk-data-prestaged-src-credentials
  labels:
    app: staging-prestaged-restore
    app.kubernetes.io/part-of: dk-data
    app.kubernetes.io/managed-by: doppler-operator
spec:
  tokenSecret:
    name: doppler-token-secret
    key: serviceToken
  project: dk-data-applications
  config: prd
  managedSecret:
    name: dk-data-prestaged-src-credentials
    type: Opaque
  resyncSeconds: 300
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: staging-prestaged-restore
  labels:
    app: staging-prestaged-restore
    app.kubernetes.io/name: staging-prestaged-restore
    app.kubernetes.io/component: prestaged-restore
    app.kubernetes.io/part-of: dk-data
    feature: 211-ws4-staging-main-reconcile
    product: dk-data
    service: dk-data
    team: data-platform
spec:
  # Prod pg-backup-daily starts 12:00 UTC with a 12h deadline; 02:00
  # next day clears it with margin.
  schedule: "0 2 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      activeDeadlineSeconds: 21600   # 6h for a ~200GB daily restore
      backoffLimit: 1
      ttlSecondsAfterFinished: 604800
      template:
        metadata:
          labels:
            app: staging-prestaged-restore
            team: data-platform
            service: dk-data
            product: dk-data
        spec:
          restartPolicy: Never
          securityContext:
            fsGroup: 1000
            runAsNonRoot: true
            seccompProfile:
              type: RuntimeDefault
          initContainers:
            - name: install-mc
              image: minio/minio:RELEASE.2024-11-07T00-52-20Z
              command: ["sh", "-c", "cp /usr/bin/mc /tmp/mc && chmod +x /tmp/mc"]
              securityContext:
                runAsNonRoot: false
                runAsUser: 0
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
              volumeMounts:
                - name: tmp
                  mountPath: /tmp
          containers:
            - name: restore
              image: ghcr.io/cloudnative-pg/postgresql:16.4
              command: ["/bin/bash", "/scripts/restore.sh"]
              env:
                - name: SRC_S3_ENDPOINT
                  value: "seaweedfs-s3.infra.svc.cluster.local:8333"
                - name: SRC_BUCKET
                  value: "postgres-backups"
                - name: SRC_S3_ACCESS_KEY
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-prestaged-src-credentials
                      key: SRC_S3_ACCESS_KEY
                - name: SRC_S3_SECRET_KEY
                  valueFrom:
                    secretKeyRef:
                      name: dk-data-prestaged-src-credentials
                      key: SRC_S3_SECRET_KEY
                - name: RESTORE_JOBS
                  value: "4"
                - name: SCRATCH_DIR
                  value: "/tmp/restore"
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
              resources:
                requests:
                  memory: "512Mi"
                  cpu: "500m"
                limits:
                  memory: "4Gi"
                  cpu: "2"
              securityContext:
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop: ["ALL"]
              volumeMounts:
                - name: restore-script
                  mountPath: /scripts
                  readOnly: true
                - name: scratch
                  mountPath: /tmp/restore
                - name: tmp
                  mountPath: /tmp
          volumes:
            - name: restore-script
              configMap:
                name: staging-prestaged-restore-script
                defaultMode: 0755
            - name: scratch
              persistentVolumeClaim:
                claimName: staging-restore-scratch
            - name: tmp
              emptyDir: {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add k8s/overlays/staging/staging-prestaged-restore.yaml tests/infra/test_staging_prestaged_restore.py
git commit -m "feat(211): staging-prestaged-restore manifest skeleton (PVC+DopplerSecret+CronJob)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: The restore script (`restore.sh`)

**Files:**
- Modify: `k8s/overlays/staging/staging-prestaged-restore.yaml` (replace the `data.restore.sh` placeholder)
- Test: `tests/infra/test_staging_prestaged_restore.py` (add script-contract tests)

- [ ] **Step 1: Add the failing tests**

Append to `tests/infra/test_staging_prestaged_restore.py`:

```python
@pytest.fixture(scope="module")
def restore_sh(docs) -> str:
    return docs["ConfigMap"]["data"]["restore.sh"]


def test_script_targets_prod_daily_prefix(restore_sh):
    assert 'SRC_PREFIX="${SRC_BUCKET}/dk-data-prod/daily/"' in restore_sh
    # latest-object selection, same idiom as verify.sh
    assert 'mc ls' not in restore_sh or '| tail -1' in restore_sh
    assert '${MC} ls "src/${SRC_PREFIX}" --json | tail -1' in restore_sh


def test_script_restore_flags(restore_sh):
    for flag in (
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--no-acl",
        '--jobs="${RESTORE_JOBS}"',
    ):
        assert flag in restore_sh, f"pg_restore must pass {flag}"


def test_script_restores_into_staging_db_not_the_store(restore_sh):
    # Restore target is the staging Postgres from dk-data-secrets, never
    # the object store creds.
    assert '-d "${POSTGRES_DB}"' in restore_sh
    assert '-h "${POSTGRES_HOST}"' in restore_sh
    assert "minio-backup-credentials" not in restore_sh


def test_script_has_integrity_gate(restore_sh):
    assert 'pg_restore --list' in restore_sh
    assert '-lt 10' in restore_sh, "must keep the >=10-object gate"
    assert "sha256sum" in restore_sh


def test_script_writes_transform_runs_breadcrumb(restore_sh):
    assert "INSERT INTO meta.transform_runs" in restore_sh
    assert "'staging-prestaged-restore'" in restore_sh
    assert "prestaged-restore-${DATESTAMP}" in restore_sh
    # NOT NULL columns from migration 172 must all be supplied.
    for col in (
        "procedure_name",
        "chunk_position",
        "started_at",
        "ended_at",
        "rows_processed",
        "wal_bytes",
    ):
        assert col in restore_sh, f"breadcrumb INSERT missing {col}"


def test_script_bash_syntax(restore_sh):
    bash = shutil.which("bash")
    assert bash, "bash required"
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(restore_sh)
        path = fh.name
    res = subprocess.run([bash, "-n", path], capture_output=True, text=True)
    assert res.returncode == 0, f"restore.sh syntax error:\n{res.stderr}"


def test_breadcrumb_failure_cannot_skip_cleanup_or_gate_job(restore_sh):
    # Approved plan deviation (Task 2 code-quality review): the
    # meta.transform_runs breadcrumb is instrumentation, not the job
    # gate. A psql failure must NOT (a) flip job status nor (b) skip the
    # ~200GB dump cleanup (else the 250Gi scratch PVC fills and the next
    # day's mc cp fails -> silent restore blackout). Cleanup must run
    # after the breadcrumb, and the breadcrumb must be set +e bracketed.
    # match the command, not the 'rm -f' inside the rationale comment
    assert restore_sh.index('rm -f "${DUMP}"') > restore_sh.index(
        "INSERT INTO meta.transform_runs"
    ), "rm -f must run AFTER the breadcrumb INSERT"
    bc = restore_sh.index("Step 6: Breadcrumb")
    assert "set +e" in restore_sh[bc:], "breadcrumb psql must be set +e bracketed"
    assert "BREADCRUMB_RC=$?" in restore_sh
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k script`
Expected: FAIL — placeholder body lacks every asserted string.

- [ ] **Step 3: Replace the placeholder script**

In `k8s/overlays/staging/staging-prestaged-restore.yaml`, replace the entire `data:` block of the `staging-prestaged-restore-script` ConfigMap with:

```yaml
data:
  restore.sh: |
    #!/bin/bash
    set -euo pipefail

    echo "=== Staging Prestaged Restore ==="
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

    MC=/tmp/mc
    export MC_CONFIG_DIR=/tmp/mc-config
    mkdir -p "${MC_CONFIG_DIR}"

    for var in SRC_S3_ENDPOINT SRC_S3_ACCESS_KEY SRC_S3_SECRET_KEY SRC_BUCKET \
               POSTGRES_HOST POSTGRES_PORT POSTGRES_USER POSTGRES_PASSWORD \
               POSTGRES_DB RESTORE_JOBS SCRATCH_DIR; do
      if [ -z "$(eval echo \$$var)" ]; then
        echo "ERROR: required variable $var is not set"
        exit 1
      fi
    done

    SRC_PREFIX="${SRC_BUCKET}/dk-data-prod/daily/"
    DUMP="${SCRATCH_DIR}/restore.dump"
    DATESTAMP="$(date -u +%Y%m%d_%H%M%S)"
    START_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    echo "--- Step 1: Configure source object store (prod SeaweedFS) ---"
    ${MC} alias set src "http://${SRC_S3_ENDPOINT}" \
      "${SRC_S3_ACCESS_KEY}" "${SRC_S3_SECRET_KEY}" --api S3v4

    echo "--- Step 2: Find latest prod daily dump ---"
    LATEST=$(${MC} ls "src/${SRC_PREFIX}" --json | tail -1)
    if [ -z "${LATEST}" ]; then
      echo "ERROR: no objects under src/${SRC_PREFIX}"
      exit 1
    fi
    KEY=$(echo "${LATEST}" | grep -o '"key":"[^"]*"' | sed 's/"key":"//;s/"//')
    echo "Latest object: ${KEY}"

    echo "--- Step 3: Download ---"
    ${MC} cp "src/${SRC_PREFIX}${KEY}" "${DUMP}"

    echo "--- Step 4: Integrity gate ---"
    OBJECT_COUNT=$(pg_restore --list "${DUMP}" | wc -l)
    echo "Object count: ${OBJECT_COUNT}"
    if [ "${OBJECT_COUNT}" -lt 10 ]; then
      echo "ERROR: integrity gate failed - only ${OBJECT_COUNT} objects"
      exit 1
    fi
    CHECKSUM=$(sha256sum "${DUMP}" | awk '{print $1}')
    echo "SHA256: ${CHECKSUM}"

    echo "--- Step 5: Restore into STAGING dk_data (in-place) ---"
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    set +e
    pg_restore \
      --clean --if-exists --no-owner --no-privileges --no-acl \
      --jobs="${RESTORE_JOBS}" \
      -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
      -d "${POSTGRES_DB}" \
      "${DUMP}"
    RESTORE_RC=$?
    set -e
    if [ "${RESTORE_RC}" -eq 0 ]; then
      STATUS="completed"
    else
      STATUS="failed"
      echo "WARN: pg_restore exited ${RESTORE_RC} (staging is a disposable"
      echo "      mirror; recording outcome and continuing)"
    fi

    # Step 6 is instrumentation. Bracket it in set +e so a transient
    # psql failure can neither flip the job's exit status (which must
    # reflect the RESTORE outcome, not the breadcrumb) nor skip the
    # dump cleanup below — a skipped rm -f fills the 250Gi scratch PVC
    # and silently blocks the next day's restore (Task 2 code-quality
    # review, approved plan deviation).
    echo "--- Step 6: Breadcrumb to meta.transform_runs ---"
    set +e
    psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
      -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
      "INSERT INTO meta.transform_runs
         (procedure_name, chunk_position, started_at, ended_at,
          rows_processed, wal_bytes, status, details)
       VALUES
         ('staging-prestaged-restore', 'all',
          '${START_TS}'::timestamptz, now(), 0, 0, '${STATUS}',
          jsonb_build_object('run_label', 'prestaged-restore-${DATESTAMP}',
                             'object', '${KEY}', 'sha256', '${CHECKSUM}',
                             'restore_rc', ${RESTORE_RC}));"
    BREADCRUMB_RC=$?
    set -e
    if [ "${BREADCRUMB_RC}" -ne 0 ]; then
      echo "WARN: breadcrumb write failed (rc=${BREADCRUMB_RC});"
      echo "      restore status was ${STATUS} — not gating the job on it"
    fi

    rm -f "${DUMP}"
    echo "--- Done: status=${STATUS} ---"
    if [ "${STATUS}" = "failed" ]; then exit 1; fi
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add k8s/overlays/staging/staging-prestaged-restore.yaml tests/infra/test_staging_prestaged_restore.py
git commit -m "feat(211): staging-prestaged-restore.sh — verified pg_restore of prod daily dump

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire into the staging overlay (and prove prod/base exclusion)

**Files:**
- Modify: `k8s/overlays/staging/kustomization.yaml:18` (the `resources:` list)
- Test: `tests/infra/test_staging_prestaged_restore.py` (add wiring + render tests)

- [ ] **Step 1: Add the failing tests**

Append to `tests/infra/test_staging_prestaged_restore.py`:

```python
def _resources(kustomization: Path) -> list[str]:
    doc = yaml.safe_load(kustomization.read_text())
    return doc.get("resources", [])


def test_staging_overlay_lists_the_resource():
    assert "staging-prestaged-restore.yaml" in _resources(STAGING_KUSTOMIZATION)


def test_prod_overlay_does_not_list_the_resource():
    res = _resources(PROD_KUSTOMIZATION)
    assert "staging-prestaged-restore.yaml" not in res
    assert not any("staging-prestaged-restore" in r for r in res)


def test_sp3_suspend_patch_does_not_match_this_cronjob():
    # The SP3 patch targets CronJob name "^fetch-.*". Static check that
    # our name is outside that regex (defence-in-depth with the
    # kubectl render test below).
    text = STAGING_KUSTOMIZATION.read_text()
    assert 'name: "^fetch-.*"' in text, "SP3 target regex changed - re-verify"
    assert not re.match(r"^fetch-.*", "staging-prestaged-restore")


@pytest.mark.skipif(
    shutil.which("kubectl") is None, reason="kubectl not on PATH"
)
def test_kustomize_render_staging_only():
    def render(overlay: str) -> list[dict]:
        out = subprocess.run(
            ["kubectl", "kustomize", str(REPO_ROOT / "k8s" / overlay)],
            capture_output=True, text=True, check=True,
        ).stdout
        return [d for d in yaml.safe_load_all(out) if d]

    staging = render("overlays/staging")
    cronjobs = {
        d["metadata"]["name"]: d
        for d in staging
        if d.get("kind") == "CronJob"
    }
    assert "staging-prestaged-restore" in cronjobs, "missing from staging render"
    # SP3 must NOT have suspended it.
    assert cronjobs["staging-prestaged-restore"]["spec"].get("suspend") in (
        None, False,
    ), "staging-prestaged-restore must stay un-suspended"
    assert cronjobs["staging-prestaged-restore"]["metadata"]["namespace"] == (
        "dk-data-staging"
    )

    prod = render("overlays/prod")
    assert "staging-prestaged-restore" not in {
        d["metadata"]["name"]
        for d in prod
        if d.get("kind") == "CronJob"
    }, "must NOT render in prod"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k "overlay or render or sp3"`
Expected: FAIL — `test_staging_overlay_lists_the_resource` fails (not yet wired).

- [ ] **Step 3: Add the resource to the staging overlay**

In `k8s/overlays/staging/kustomization.yaml`, the `resources:` block currently reads:

```yaml
resources:
- ../../base
- ../../apps/secrets/per-source
```

Change it to:

```yaml
resources:
- ../../base
- ../../apps/secrets/per-source
# WS4 SP3 follow-on (feature 211) — staging-only prestaged restore.
# Spec: docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md
- staging-prestaged-restore.yaml
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v`
Expected: PASS. (The `kubectl` render test runs if `kubectl` is present; otherwise it is skipped — the static wiring tests still cover the contract.)

- [ ] **Step 5: Manually sanity-render (if kubectl available)**

Run: `kubectl kustomize k8s/overlays/staging | grep -A2 "name: staging-prestaged-restore"`
Expected: the CronJob appears with `namespace: dk-data-staging` and no `suspend: true`.
Run: `kubectl kustomize k8s/overlays/prod | grep -c staging-prestaged-restore`
Expected: `0`.

- [ ] **Step 6: Commit**

```bash
git add k8s/overlays/staging/kustomization.yaml tests/infra/test_staging_prestaged_restore.py
git commit -m "feat(211): wire staging-prestaged-restore into the staging overlay only

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Failure alert (`PrometheusRule`, hand-applied convention)

**Files:**
- Create: `grafana/alerts/staging-prestaged-restore.yaml`
- Test: `tests/infra/test_staging_prestaged_restore.py` (add alert tests)

- [ ] **Step 1: Add the failing tests**

Append to `tests/infra/test_staging_prestaged_restore.py`:

```python
ALERT = REPO_ROOT / "grafana" / "alerts" / "staging-prestaged-restore.yaml"


@pytest.fixture(scope="module")
def alert_doc() -> dict:
    return yaml.safe_load(ALERT.read_text())


def test_alert_is_a_prometheusrule(alert_doc):
    assert alert_doc["apiVersion"] == "monitoring.coreos.com/v1"
    assert alert_doc["kind"] == "PrometheusRule"
    assert alert_doc["metadata"]["namespace"] == "dk-data-staging"


def test_alert_targets_the_restore_job_failure(alert_doc):
    rules = [
        r
        for g in alert_doc["spec"]["groups"]
        for r in g["rules"]
    ]
    exprs = " ".join(r["expr"] for r in rules)
    assert "kube_job_status_failed" in exprs
    assert 'job_name=~"staging-prestaged-restore.*"' in exprs
    assert 'namespace="dk-data-staging"' in exprs
    assert any(r["labels"]["service"] == "dk-data" for r in rules)


def test_alert_pins_both_alert_names_and_staleness_expr(alert_doc):
    rules = [
        r
        for g in alert_doc["spec"]["groups"]
        for r in g["rules"]
    ]
    exprs = " ".join(r["expr"] for r in rules)
    alert_names = {r["alert"] for r in rules}
    assert "StagingPrestagedRestoreFailed" in alert_names
    assert "StagingPrestagedRestoreStale" in alert_names
    assert "kube_job_status_completion_time" in exprs
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k alert`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Create the PrometheusRule**

Create `grafana/alerts/staging-prestaged-restore.yaml`:

```yaml
# Feature 211 WS4 SP3 follow-on — staging prestaged restore health.
# Spec: docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md
#
# Convention mirrors grafana/alerts/gold-zero-rows.yaml: this
# PrometheusRule is orphaned from kustomization on purpose. Operators
# apply it by hand once the shared-infra prometheus-operator install is
# coordinated:
#
#   kubectl -n dk-data-staging apply -f grafana/alerts/staging-prestaged-restore.yaml
#
# Depends on kube-state-metrics emitting kube_job_status_failed (already
# scraped into the cluster Prometheus/Mimir). If kube-state-metrics is
# absent the rule is simply inert (NoData), not a false positive.
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: staging-prestaged-restore
  namespace: dk-data-staging
  labels:
    app.kubernetes.io/name: dk-data
    app.kubernetes.io/component: alert
    app.kubernetes.io/part-of: dk-data
spec:
  groups:
    - name: dk-data.staging.prestaged_restore
      interval: 5m
      rules:
        # Any failed restore Job in the last 24h. Staging raw goes stale
        # if this keeps failing while SP3 has the fetchers suspended.
        - alert: StagingPrestagedRestoreFailed
          expr: |
            max_over_time(
              kube_job_status_failed{
                namespace="dk-data-staging",
                job_name=~"staging-prestaged-restore.*"
              }[24h]
            ) > 0
          for: 10m
          labels:
            severity: warning
            service: dk-data
            component: prestaged-restore
          annotations:
            summary: "staging-prestaged-restore Job failed in the last 24h"
            description: |
              The staging prestaged-restore CronJob
              (k8s/overlays/staging/staging-prestaged-restore.yaml) has a
              failed Job in the last 24h. With WS4 SP3 suspending staging
              ^fetch-* CronJobs, a persistently failing restore means
              staging's dk_data raw layer is going stale.

              Investigate:
                - kubectl -n dk-data-staging get jobs.batch | grep staging-prestaged-restore
                - kubectl -n dk-data-staging logs job/<latest> -c restore
                - psql ... -c "SELECT status, details, ended_at FROM meta.transform_runs WHERE procedure_name='staging-prestaged-restore' ORDER BY ended_at DESC LIMIT 5;"

              Rollback (resume staging fetchers): delete the
              staging-prestaged-restore.yaml line from
              k8s/overlays/staging/kustomization.yaml AND revert the SP3
              ^fetch-* suspend patch.

              Runbook: docs/runbooks/staging-prestaged-restore.md

        # No successful restore for >36h (job not scheduled / stuck).
        - alert: StagingPrestagedRestoreStale
          expr: |
            time() - max(
              kube_job_status_completion_time{
                namespace="dk-data-staging",
                job_name=~"staging-prestaged-restore.*"
              }
            ) > 36 * 3600
          for: 30m
          labels:
            severity: warning
            service: dk-data
            component: prestaged-restore
          annotations:
            summary: "No successful staging prestaged restore in >36h"
            description: |
              No staging-prestaged-restore Job has completed in >36h
              (expected daily at 02:00 UTC). Staging raw data is
              stale relative to prod. See
              docs/runbooks/staging-prestaged-restore.md.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k alert`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grafana/alerts/staging-prestaged-restore.yaml tests/infra/test_staging_prestaged_restore.py
git commit -m "feat(211): PrometheusRule for staging-prestaged-restore failure/staleness

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Grafana dashboard (restore status + job failure)

**Files:**
- Create: `grafana/dashboards/applications/dk-data-fe-staging-prestaged-restore.json`
- Test: `tests/infra/test_staging_prestaged_restore.py` (add dashboard tests)

- [ ] **Step 1: Add the failing tests**

Append to `tests/infra/test_staging_prestaged_restore.py`:

```python
DASHBOARD = (
    REPO_ROOT
    / "grafana"
    / "dashboards"
    / "applications"
    / "dk-data-fe-staging-prestaged-restore.json"
)


def test_dashboard_is_valid_json_with_expected_shape():
    doc = json.loads(DASHBOARD.read_text())
    dash = doc["dashboard"]
    assert dash["uid"] == "dk-data-fe-staging-prestaged-restore"
    assert "feature-211" in dash["tags"]
    panels = dash["panels"]
    exprs_sql = " ".join(
        t.get("rawSql", "")
        for p in panels
        for t in p.get("targets", [])
    )
    exprs_prom = " ".join(
        t.get("expr", "")
        for p in panels
        for t in p.get("targets", [])
    )
    assert "meta.transform_runs" in exprs_sql
    assert "staging-prestaged-restore" in exprs_sql
    assert "kube_job_status_failed" in exprs_prom
    assert "kube_job_status_completion_time" in exprs_prom
    assert len(panels) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k dashboard`
Expected: FAIL — `FileNotFoundError`.

- [ ] **Step 3: Create the dashboard**

Create `grafana/dashboards/applications/dk-data-fe-staging-prestaged-restore.json`:

```json
{
  "__metadata": { "folder": "applications" },
  "dashboard": {
    "annotations": { "list": [] },
    "description": "WS4 SP3 follow-on (feature 211): staging prestaged restore health. Tracks the latest pg_restore outcome of prod's daily dump into staging and any restore-Job failures.",
    "editable": true,
    "graphTooltip": 1,
    "id": null,
    "panels": [
      {
        "id": 1,
        "type": "table",
        "title": "Recent staging prestaged restores",
        "datasource": { "type": "postgres", "uid": "postgres" },
        "gridPos": { "h": 9, "w": 24, "x": 0, "y": 0 },
        "targets": [
          {
            "refId": "A",
            "datasource": { "type": "postgres", "uid": "postgres" },
            "format": "table",
            "rawSql": "SELECT ended_at, status, details->>'object' AS object, details->>'sha256' AS sha256, details->>'run_label' AS run_label FROM meta.transform_runs WHERE procedure_name = 'staging-prestaged-restore' ORDER BY ended_at DESC LIMIT 20;"
          }
        ]
      },
      {
        "id": 2,
        "type": "stat",
        "title": "Restore Job failures (24h, must stay 0)",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "gridPos": { "h": 5, "w": 12, "x": 0, "y": 9 },
        "fieldConfig": {
          "defaults": {
            "color": { "mode": "thresholds" },
            "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "red", "value": 1 } ] }
          },
          "overrides": []
        },
        "options": {
          "colorMode": "background",
          "graphMode": "area",
          "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }
        },
        "targets": [
          {
            "refId": "A",
            "datasource": { "type": "prometheus", "uid": "prometheus" },
            "expr": "max_over_time(kube_job_status_failed{namespace=\"dk-data-staging\", job_name=~\"staging-prestaged-restore.*\"}[24h])",
            "legendFormat": "failed"
          }
        ]
      },
      {
        "id": 3,
        "type": "stat",
        "title": "Hours since last successful restore",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "gridPos": { "h": 5, "w": 12, "x": 12, "y": 9 },
        "fieldConfig": { "defaults": { "unit": "h", "color": { "mode": "thresholds" }, "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "red", "value": 36 } ] } }, "overrides": [] },
        "options": {
          "colorMode": "value",
          "graphMode": "none",
          "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }
        },
        "targets": [
          {
            "refId": "A",
            "datasource": { "type": "prometheus", "uid": "prometheus" },
            "expr": "(time() - max(kube_job_status_completion_time{namespace=\"dk-data-staging\", job_name=~\"staging-prestaged-restore.*\"})) / 3600",
            "legendFormat": "hours"
          }
        ]
      }
    ],
    "refresh": "5m",
    "schemaVersion": 39,
    "style": "dark",
    "tags": ["dk-data", "staging", "prestaged-restore", "feature-211", "ws4"],
    "templating": { "list": [] },
    "time": { "from": "now-7d", "to": "now" },
    "timezone": "",
    "title": "dk-data Staging Prestaged Restore",
    "uid": "dk-data-fe-staging-prestaged-restore",
    "version": 1,
    "weekStart": ""
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v -k dashboard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add grafana/dashboards/applications/dk-data-fe-staging-prestaged-restore.json tests/infra/test_staging_prestaged_restore.py
git commit -m "feat(211): Grafana dashboard for staging prestaged restore

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Operator runbook + full-suite green

**Files:**
- Create: `docs/runbooks/staging-prestaged-restore.md`
- Test: full `tests/infra/test_staging_prestaged_restore.py` run

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/staging-prestaged-restore.md`:

```markdown
# Runbook — staging prestaged restore

**What:** staging consumes prod's existing `pg-backup-daily` artifact
instead of re-fetching every external source (WS4 SP3 / feature 211).
Spec: `docs/superpowers/specs/2026-05-19-staging-prestaged-restore-design.md`.

## Operator preconditions (MUST be true before SP3 is ArgoCD-synced)

1. **Source creds.** Doppler `dk-data-applications/prd` has read-only
   keys `SRC_S3_ACCESS_KEY` / `SRC_S3_SECRET_KEY` for prod SeaweedFS
   bucket `postgres-backups`. The `dk-data-prestaged-src-credentials`
   DopplerSecret materialises these into `dk-data-staging`.
2. **Egress.** `dk-data-staging` can reach
   `seaweedfs-s3.infra.svc.cluster.local:8333`. If a default-deny
   NetworkPolicy exists in `dk-data-staging`, add an egress allow to the
   `infra` SeaweedFS service.
3. **Disk.** Staging Postgres has ≥ ~250 GB free for the restored daily
   dataset; the `staging-restore-scratch` PVC requests 250 Gi.
4. **Ordering.** Merge + green-run this restore **before** SP3's
   `^fetch-*` suspension is ArgoCD-synced to staging. Otherwise staging
   raw goes stale between suspension and first restore (degraded
   *staging only*, fully reversible).

## Manual trigger

```
kubectl -n dk-data-staging create job \
  --from=cronjob/staging-prestaged-restore \
  staging-prestaged-restore-$(date +%Y%m%d%H%M)
kubectl -n dk-data-staging logs -f job/staging-prestaged-restore-<ts> -c restore
```

## Verify

```
psql ... -c "SELECT status, ended_at, details->>'object'
             FROM meta.transform_runs
             WHERE procedure_name='staging-prestaged-restore'
             ORDER BY ended_at DESC LIMIT 5;"
```

Dashboard: **dk-data Staging Prestaged Restore**
(`uid=dk-data-fe-staging-prestaged-restore`).
Alerts: `grafana/alerts/staging-prestaged-restore.yaml` (apply by hand,
mirrors the `gold-zero-rows.yaml` convention).

## Rollback (resume staging fetchers)

1. Delete the `staging-prestaged-restore.yaml` line from
   `k8s/overlays/staging/kustomization.yaml`.
2. Revert the SP3 `^fetch-*` suspend patch in the same file.

Instant, staging-only, no data loss (prod untouched throughout).
```

- [ ] **Step 2: Run the full infra test file**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/test_staging_prestaged_restore.py -v`
Expected: PASS (all tests; the `kubectl` render test passes if `kubectl` present, else skipped).

- [ ] **Step 3: Run the broader infra suite for regressions**

Run: `/Users/nick/Code/dk-data-FE/.venv/bin/python -m pytest tests/infra/ -q`
Expected: PASS / no new failures (pre-existing unrelated failures, if any, are noise — confirm none reference `staging-prestaged-restore`).

- [ ] **Step 4: Commit**

```bash
git add docs/runbooks/staging-prestaged-restore.md
git commit -m "docs(211): staging prestaged restore operator runbook

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (each spec section → task):

- *Strategy / data flow (Approach A, daily source)* → Tasks 1–2 (manifest + `restore.sh` reading `dk-data-prod/daily/`).
- *The new component table (name, image, initContainer, steps, scratch, schedule, restore semantics)* → Task 1 (manifest contract tests) + Task 2 (`--clean --if-exists --no-owner --no-privileges --no-acl`, integrity gate).
- *Credentials & overlay wiring (prod-store creds; staging-overlay-only)* → Task 1 (`DopplerSecret config: prd`) + Task 3 (resource in staging only; prod/base exclusion + render test) + `test_sp3_suspend_patch_does_not_match_this_cronjob`.
- *Observability (transform_runs breadcrumb + kube-state alert)* → Task 2 (`INSERT INTO meta.transform_runs`) + Task 4 (`PrometheusRule`) + Task 5 (dashboard).
- *Tests (script assertion, kustomize render, manifest shape)* → Tasks 1–5 tests, all offline; render test `kubectl`-guarded.
- *Rollback + operator preconditions* → Task 6 runbook + alert annotations.
- *Out of scope (no producer, no per-source tree, no prod change)* → enforced by `test_prod_overlay_does_not_list_the_resource` + `test_kustomize_render_staging_only`.

**Placeholder scan:** Task 1 intentionally ships a `placeholder` script body that is *immediately* replaced and tested in Task 2 (the test in Task 2 fails until the real script lands) — this is staged TDD, not a plan placeholder. No `TBD`/`TODO`/"handle errors"/uncoded steps remain.

**Type/name consistency:** `staging-prestaged-restore` (CronJob), `staging-restore-scratch` (PVC), `staging-prestaged-restore-script` (ConfigMap), `dk-data-prestaged-src-credentials` (DopplerSecret), env names (`SRC_S3_ENDPOINT`, `SRC_BUCKET`, `SRC_S3_ACCESS_KEY`, `SRC_S3_SECRET_KEY`, `RESTORE_JOBS`, `SCRATCH_DIR`, `POSTGRES_*`), `meta.transform_runs` columns (`procedure_name, chunk_position, started_at, ended_at, rows_processed, wal_bytes, status, details`) and dashboard `uid` are identical across the manifest, the script, the tests, the alert, the dashboard, and the runbook.

---

## Task 7: Reconcile the dashboard with the pre-existing observability smoke contract (CI-discovered plan defect)

**Discovered:** PR #435 CI `Test` job red. `tests/observability/test_dashboard_smoke.py::TestMetricReferences::test_each_dashboard_references_at_least_one_defined_metric` flagged `dk-data-fe-staging-prestaged-restore.json` as an offender. **Plan defect:** Tasks 1–6 never accounted for this pre-existing repo-wide contract; the local gate (`tests/infra/`) does not exercise `tests/observability/`. Not an implementation defect — the dashboard JSON is exactly as specified.

**Root cause (verified):** the smoke test accepts a dashboard only if (a) some panel expr references a metric defined in `src/dk_data/observability/metrics.py` / `metering_proxy/metrics.py`, **or** (b) every non-row panel datasource ∈ `{postgres, loki, ""}`. Our dashboard is `{postgres, prometheus}` and its only Prometheus metrics are kube-state (`kube_job_status_failed`, `kube_job_status_completion_time`) — not in the dk-data registry (the restore is an out-of-band bash `pg_restore` CronJob, not the feature-005 `prestaged.py` Python path, so it emits no dk-data app metric). It is a legitimate "postgres breadcrumb + kube-state job-health" dashboard the fallback never anticipated, even though the same file already curates an `EXTERNAL_METRICS` allowlist (kube/node/pg/process) — which this *smoke* test does not consult (only the exhaustive T115 test does).

**Approved resolution (Fix C — operator-chosen over reworking the dashboard):** treat a known-external metric reference as satisfying the smoke test, exactly as a defined-registry metric is. Scope: `tests/observability/test_dashboard_smoke.py` only (out of Tasks 1–6 file scope; approved deviation).

- [ ] **Step 1:** Add `kube_job_status_failed` and `kube_job_status_completion_time` to `EXTERNAL_METRICS`.
- [ ] **Step 2:** Extract the per-dashboard accept decision into a module helper `_dashboard_is_connected(d, defined_metrics) -> bool` that preserves the existing logic byte-faithfully (defined-metric substring match → `True`; else pg/loki/"" datasource fallback) **plus** one added branch: a reference to a known-external metric also returns `True`. Exclude the histogram-suffix noise entries (`_bucket`/`_count`/`_sum`, i.e. `m.startswith("_")`) from the external-acceptance set so an undefined/typo'd *app* metric still cannot pass (contract not weakened). Rewrite `test_each_dashboard_references_at_least_one_defined_metric` to use the helper.
- [ ] **Step 3:** Add regression tests: `test_kube_job_status_metrics_are_allowlisted` (membership) and `test_external_metric_only_dashboard_is_connected` (synthetic postgres+`kube_job_status_failed` dashboard → connected; red before Fix C, green after).
- [ ] **Step 4:** Verify locally: `tests/observability/ -q --no-cov` all green (was 9 passed + 1 failed → now ≥11 passed, 0 failed); `tests/infra/ -q --no-cov` still 26 passed (no cross-impact). Independent review of behavior-preservation + no app-metric-typo weakening.
- [ ] **Step 5:** Commit `fix(211): accept known-external (kube-state) metrics in dashboard smoke test`. Push; re-run PR #435 CI; confirm `Test` + all required checks green before merge.

**Blast radius (verified zero-regression):** the change only ever flips a *currently-failing* dashboard to pass, and only if its non-pg/loki exprs reference an allowlisted external metric; it cannot make any currently-passing dashboard fail, and cannot make an undefined dk-data app-metric reference pass (those names are in neither `defined_metrics` nor the cleaned `EXTERNAL_METRICS`). Consistent with the test's own documented "smoke, not pedantic — exhaustive auditing is T115" scope.
