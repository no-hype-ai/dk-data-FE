"""T024d — Metering proxy HA validation.

Verifies the static invariants that make the proxy deployment
tolerant of voluntary disruption:

  - The kustomize base includes a PodDisruptionBudget with
    `minAvailable: 1`
  - The PDB's selector matches the proxy's pod labels

The dynamic failover test (kill one replica, measure recovery time)
runs against a real cluster — see
`docs/reports/metering-proxy-failover-test.md` for the procedure
and expected timing. This file guards the static manifest so a
future PR can't silently drop the PDB.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PDB_FILE = REPO_ROOT / "k8s" / "apps" / "metering-proxy" / "base" / "pdb.yaml"
KUSTOMIZATION_FILE = (
    REPO_ROOT / "k8s" / "apps" / "metering-proxy" / "base" / "kustomization.yaml"
)


@pytest.fixture
def pdb_doc():
    assert PDB_FILE.exists(), f"missing PDB: {PDB_FILE}"
    return yaml.safe_load(PDB_FILE.read_text())


@pytest.fixture
def kustomization_doc():
    return yaml.safe_load(KUSTOMIZATION_FILE.read_text())


class TestPodDisruptionBudget:
    def test_pdb_is_present(self, pdb_doc):
        assert pdb_doc["kind"] == "PodDisruptionBudget"

    def test_api_version_is_policy_v1(self, pdb_doc):
        assert pdb_doc["apiVersion"] == "policy/v1"

    def test_min_available_is_at_least_1(self, pdb_doc):
        assert pdb_doc["spec"]["minAvailable"] == 1

    def test_selector_matches_component(self, pdb_doc):
        labels = pdb_doc["spec"]["selector"]["matchLabels"]
        assert labels.get("app.kubernetes.io/component") == "metering-proxy"

    def test_kustomization_includes_pdb(self, kustomization_doc):
        assert "pdb.yaml" in kustomization_doc["resources"]
