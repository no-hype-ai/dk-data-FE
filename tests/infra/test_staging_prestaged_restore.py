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
    assert restore_sh.index('rm -f "${DUMP}"') > restore_sh.index(
        "INSERT INTO meta.transform_runs"
    ), "rm -f must run AFTER the breadcrumb INSERT"
    bc = restore_sh.index("Step 6: Breadcrumb")
    assert "set +e" in restore_sh[bc:], "breadcrumb psql must be set +e bracketed"
    assert "BREADCRUMB_RC=$?" in restore_sh
