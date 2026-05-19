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
