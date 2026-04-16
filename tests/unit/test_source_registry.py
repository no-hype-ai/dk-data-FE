"""Unit tests for ``dk_data.ingestion.source_registry``.

Feature: Horizon 3 / plan §D.2 — declarative source descriptors.

Coverage (6 tests per the D.2 scope):
  1. Descriptor load happy path.
  2. Missing required fields surface a clear error.
  3. Invalid tier rejected.
  4. ``sync_to_db`` upserts (fake connection, mocked pool).
  5. ``load_all`` walks a directory and skips ``_schema.yaml``.
  6. Round-trip: serialize → reload → equal.

FR-030: ``sync_to_db`` is exercised with an injected fake connection so the
tests never import psycopg2.connect directly.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

from dk_data.ingestion.source_registry import (
    DescriptorValidationError,
    SourceDescriptor,
    load_all,
    load_descriptor,
    sync_to_db,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_descriptor_dict() -> Dict[str, Any]:
    """A minimal-but-complete, schema-valid descriptor."""
    return {
        "name": "chembl_molecules",
        "domain": "mol",
        "tier": 2,
        "depends_on": [],
        "fetch": {
            "kind": "postgres_dump",
            "artifact_uri": "s3://dk-data-prestaged/chembl/molecules.dump",
        },
        "schedule": "0 3 1 * *",
        "credentials_ref": "none",
        "expected_row_count_fn": "SELECT 1",
        "sla_seconds": 1800,
        "manifest": ".dk/sources/chembl_molecules.manifest.json",
        "consumes": {"wal_headroom_pct": 5, "db_connections": 2},
    }


def _write(tmp_path: Path, name: str, body: Dict[str, Any]) -> Path:
    """Helper: write ``body`` to ``tmp_path / {name}.yaml`` and return path."""
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fake DB plumbing — no real psycopg2 connection. Emulates just enough of
# cursor().execute + fetchone() for sync_to_db's INSERT … RETURNING.
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Emulates the psycopg2 cursor contract used by sync_to_db.

    Returns ``(True,)`` from ``fetchone()`` on the first upsert per name
    (simulating a fresh insert) and ``(False,)`` thereafter (simulating an
    update). The real upsert uses ``xmax = 0`` to distinguish insert vs
    update; we mimic that truthy-inserted contract so the summary counters
    line up.
    """

    def __init__(self, state: Dict[str, Any]) -> None:
        self._state = state
        self._last: Optional[Tuple[Any, ...]] = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: Dict[str, Any]) -> None:
        self._state["executions"].append((sql, dict(params)))
        name = params["name"]
        inserted = name not in self._state["rows"]
        self._state["rows"][name] = dict(params)
        self._last = (inserted,)

    def fetchone(self) -> Optional[Tuple[Any, ...]]:
        return self._last


class _FakeConn:
    def __init__(self) -> None:
        self.state: Dict[str, Any] = {"executions": [], "rows": {}}
        self.autocommit = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.state)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadDescriptor:
    def test_happy_path_returns_validated_dataclass(
        self, tmp_path: Path, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 1: a valid descriptor parses into a frozen dataclass with
        all required fields populated and optionals preserved."""
        path = _write(tmp_path, "chembl_molecules", valid_descriptor_dict)

        desc = load_descriptor(path)

        assert isinstance(desc, SourceDescriptor)
        assert desc.name == "chembl_molecules"
        assert desc.domain == "mol"
        assert desc.tier == 2
        assert desc.depends_on == ()
        assert desc.fetch["kind"] == "postgres_dump"
        assert desc.fetch["artifact_uri"].startswith("s3://")
        assert desc.sla_seconds == 1800
        assert desc.expected_row_count_fn == "SELECT 1"
        assert desc.consumes["db_connections"] == 2
        # Frozen: attempting to mutate raises.
        with pytest.raises(Exception):
            desc.name = "other"  # type: ignore[misc]

    def test_missing_required_field_raises(
        self, tmp_path: Path, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 2: dropping a required field surfaces a clear validation
        error that names the missing field."""
        bad = dict(valid_descriptor_dict)
        bad.pop("tier")
        path = _write(tmp_path, "chembl_molecules", bad)

        with pytest.raises(DescriptorValidationError) as exc:
            load_descriptor(path)
        assert "tier" in str(exc.value)

    def test_invalid_tier_rejected(
        self, tmp_path: Path, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 3: tier must be an integer in [1,8]; 0 and 99 both fail."""
        bad = dict(valid_descriptor_dict)
        bad["tier"] = 99
        path = _write(tmp_path, "chembl_molecules", bad)

        with pytest.raises(DescriptorValidationError) as exc:
            load_descriptor(path)
        assert "tier" in str(exc.value)


class TestSyncToDb:
    def test_upserts_descriptors_via_injected_connection(
        self, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 4: sync_to_db upserts each descriptor via an injected
        connection (FR-030: no raw psycopg2.connect). A second call with
        the same descriptor registers as an update, not a new insert."""
        desc_a = SourceDescriptor(
            name=valid_descriptor_dict["name"],
            domain=valid_descriptor_dict["domain"],
            tier=valid_descriptor_dict["tier"],
            depends_on=tuple(valid_descriptor_dict["depends_on"]),
            fetch=dict(valid_descriptor_dict["fetch"]),
            schedule=valid_descriptor_dict["schedule"],
            credentials_ref=valid_descriptor_dict["credentials_ref"],
            sla_seconds=valid_descriptor_dict["sla_seconds"],
            expected_row_count_fn=valid_descriptor_dict["expected_row_count_fn"],
            manifest=valid_descriptor_dict["manifest"],
            consumes=dict(valid_descriptor_dict["consumes"]),
        )
        desc_b = replace(desc_a, name="openfda_enforcement", fetch={"kind": "http_json_paginated", "url": "https://example.test/e"})

        conn = _FakeConn()
        summary = sync_to_db([desc_a, desc_b], conn=conn)
        assert summary == {"inserted": 2, "updated": 0, "total": 2}
        assert len(conn.state["executions"]) == 2
        # Each execution targets meta.source_registry.
        for sql, _params in conn.state["executions"]:
            assert "meta.source_registry" in sql
            assert "ON CONFLICT (name) DO UPDATE" in sql

        # Re-sync: same names → all updates.
        summary2 = sync_to_db([desc_a, desc_b], conn=conn)
        assert summary2 == {"inserted": 0, "updated": 2, "total": 2}


class TestLoadAll:
    def test_walks_directory_and_skips_schema_file(
        self, tmp_path: Path, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 5: load_all returns every *.yaml except those starting
        with ``_`` (the schema file)."""
        _write(tmp_path, "chembl_molecules", valid_descriptor_dict)

        second = dict(valid_descriptor_dict)
        second["name"] = "cms_open_payments"
        second["domain"] = "hcs"
        second["tier"] = 5
        second["fetch"] = {"kind": "http_csv", "url": "https://example.test/cms.csv"}
        _write(tmp_path, "cms_open_payments", second)

        # The schema file must not be loaded (underscore prefix).
        (tmp_path / "_schema.yaml").write_text("version: 1\n", encoding="utf-8")

        descriptors = load_all(tmp_path)
        names = sorted(d.name for d in descriptors)
        assert names == ["chembl_molecules", "cms_open_payments"]


class TestRoundTrip:
    def test_serialize_and_reload_equal(
        self, tmp_path: Path, valid_descriptor_dict: Dict[str, Any]
    ) -> None:
        """Scenario 6: to_dict → YAML → load_descriptor produces an equal
        SourceDescriptor (frozen dataclass equality)."""
        path = _write(tmp_path, "chembl_molecules", valid_descriptor_dict)
        first = load_descriptor(path)

        reserialised = tmp_path / "chembl_molecules_round.yaml"
        body = first.to_dict()
        body["name"] = "chembl_molecules_round"  # filename stem must match name
        reserialised.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")

        second = load_descriptor(reserialised)
        # Names differ only because load_descriptor enforces filename stem ==
        # name. All other fields must match exactly.
        assert replace(second, name=first.name) == first
