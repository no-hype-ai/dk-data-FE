"""Regression guard for the pg-backup daily/weekly dump split.

Context: the daily pg-backup CronJob DeadlineExceeded mid-pubchem COPY
even at the 12h deadline because two SQLMesh bronze tables
(mol_bronze chembl_activities ~122GB + pubchem ~111GB, ~54% of the
434GB DB) cannot be dumped inside any single daily window. The B-part
fix excludes ONLY those two, ONLY for the daily backup; the WEEKLY
backup must remain a FULL dump (it is the recovery source for them).
Mesh handoff 2026-05-05 cluster-recovery (B-part); issue #406.

These assertions pin the contract so the split cannot silently
regress (e.g. an unconditional exclude that also strips weekly, or
losing the daily-only gate).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGMAP = (
    REPO_ROOT
    / "k8s"
    / "apps"
    / "infrastructure"
    / "base"
    / "backup"
    / "pg-backup-configmap.yaml"
)


@pytest.fixture(scope="module")
def backup_sh() -> str:
    doc = yaml.safe_load(CONFIGMAP.read_text())
    return doc["data"]["backup.sh"]


def test_daily_excludes_both_oversized_tables(backup_sh: str):
    assert "--exclude-table='mol_bronze.*chembl_activities*'" in backup_sh, (
        "daily backup must exclude the oversized chembl_activities bronze table"
    )
    assert "--exclude-table='mol_bronze.*pubchem*'" in backup_sh, (
        "daily backup must exclude the oversized pubchem bronze table"
    )


def test_exclusion_is_gated_on_daily_only(backup_sh: str):
    # The exclude args must be set inside a `BACKUP_TYPE = daily` branch,
    # never unconditionally — otherwise the weekly full backup loses the
    # two tables and there is no recovery source for them.
    assert 'if [ "${BACKUP_TYPE}" = "daily" ]; then' in backup_sh
    gate_idx = backup_sh.index('if [ "${BACKUP_TYPE}" = "daily" ]; then')
    assign_idx = backup_sh.index("EXCLUDE_ARGS=(--exclude-table=")
    assert gate_idx < assign_idx, (
        "EXCLUDE_ARGS must be populated *after* the daily gate opens, "
        "not unconditionally"
    )


def test_pg_dump_uses_array_expansion(backup_sh: str):
    # Quoted array expansion → empty for weekly (full dump), glob-safe
    # for daily (the patterns contain '*').
    assert 'EXCLUDE_ARGS=()' in backup_sh, "must default to an empty array"
    assert '"${EXCLUDE_ARGS[@]}"' in backup_sh, (
        "pg_dump must consume the exclude args via quoted array expansion"
    )


def test_weekly_path_assigns_no_exclude_args(backup_sh: str):
    # The ONLY assignment to a non-empty EXCLUDE_ARGS must live inside the
    # daily gate. Statically guarantees the weekly (and any non-daily)
    # path keeps the empty default → a full dump — without depending on
    # the host bash version's empty-array-under-`set -u` semantics
    # (prod runs bash 5.2; dev macOS ships bash 3.2).
    populating = [
        ln.strip()
        for ln in backup_sh.splitlines()
        if "EXCLUDE_ARGS=(--exclude-table=" in ln
    ]
    assert len(populating) == 1, (
        f"expected exactly one populating EXCLUDE_ARGS assignment, "
        f"found {len(populating)}: {populating}"
    )
    before_gate = backup_sh.split(
        'if [ "${BACKUP_TYPE}" = "daily" ]; then'
    )[0]
    assert "EXCLUDE_ARGS=(--exclude-table=" not in before_gate, (
        "EXCLUDE_ARGS must not be populated before the daily gate"
    )


def test_extracted_script_has_valid_bash_syntax(backup_sh: str):
    bash = shutil.which("bash")
    assert bash, "bash required for this test"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False
    ) as fh:
        fh.write(backup_sh)
        path = fh.name
    result = subprocess.run([bash, "-n", path], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"backup.sh has a bash syntax error:\n{result.stderr}"
    )
