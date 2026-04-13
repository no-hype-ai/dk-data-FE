"""Regression guard: every schema referenced by consumers.yaml must be
known to `schemas.KNOWN_SCHEMAS`.

Feature: 002-external-integration-foundation (drift audit)

Background: if a PR adds a new schema to a consumer's allowlist in
consumers.yaml but forgets to add it to `KNOWN_SCHEMAS` in schemas.py,
the metering proxy will silently treat requests to that schema as
default-schema (`api`) requests. The allowlist check then passes or
fails based on whether the consumer has `api` in their list, NOT
based on the intended schema — a classic drift footgun.

This test pins both sides together.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dk_data.metering_proxy.schemas import KNOWN_SCHEMAS

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSUMERS_CONFIGMAP = (
    REPO_ROOT / "k8s" / "apps" / "metering-proxy" / "base" / "configmap.yaml"
)


def _load_configmap_consumers() -> dict:
    """Pull the `consumers.yaml` embedded in the ConfigMap."""
    raw = yaml.safe_load(CONSUMERS_CONFIGMAP.read_text())
    nested = raw["data"]["consumers.yaml"]
    return yaml.safe_load(nested)


@pytest.fixture(scope="module")
def consumers_config() -> dict:
    return _load_configmap_consumers()


class TestSchemaAllowlistCoverage:
    def test_every_allowlisted_schema_is_known(self, consumers_config):
        """No consumer should reference a schema that `schemas.py` doesn't know about."""
        all_referenced: set[str] = set()
        for _, consumer in consumers_config["consumers"].items():
            for s in consumer.get("allowed_schemas", []):
                if s == "*":
                    continue
                all_referenced.add(s)

        unknown = all_referenced - KNOWN_SCHEMAS
        assert not unknown, (
            f"Consumers reference schemas that schemas.KNOWN_SCHEMAS does not recognize: "
            f"{sorted(unknown)}. Requests to these schemas will silently fall through to "
            "the 'api' default and bypass the per-schema allowlist. Add them to "
            "src/dk_data/metering_proxy/schemas.py:KNOWN_SCHEMAS."
        )

    def test_no_consumer_uses_wildcard(self, consumers_config):
        """T020: the `internal` consumer (and every other) must have an explicit allowlist."""
        wildcard_consumers: list[str] = []
        for name, consumer in consumers_config["consumers"].items():
            if "*" in consumer.get("allowed_schemas", []):
                wildcard_consumers.append(name)
        assert not wildcard_consumers, (
            f"Consumers still use wildcard allowlist: {wildcard_consumers}. "
            "T020 requires an explicit allowlist for every consumer, including `internal`."
        )

    def test_every_consumer_has_allowed_schemas(self, consumers_config):
        missing: list[str] = []
        for name, consumer in consumers_config["consumers"].items():
            if not consumer.get("allowed_schemas"):
                missing.append(name)
        assert not missing, f"consumers with empty allowed_schemas: {missing}"

    def test_behavior_labs_ai_allowlist_covers_t021(self, consumers_config):
        """T021: behavior-labs-ai must have ip_api + silver schemas in its allowlist."""
        blai = consumers_config["consumers"]["behavior-labs-ai"]
        required = {"ip_api", "mol_silver", "mol_gold", "ip_silver"}
        missing = required - set(blai["allowed_schemas"])
        assert not missing, (
            f"behavior-labs-ai allowlist missing T021 schemas: {missing}"
        )
