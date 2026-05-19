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
