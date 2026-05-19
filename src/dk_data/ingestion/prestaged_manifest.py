"""Manifest loader + row-count gate for 005-prestaged-hydration (PR-02).

See:
  - plan.md §A.1 (truncation diagnosis) — why the gate exists.
  - plan.md §B.3 — the contract this module implements.
  - ``src/dk_data/ingestion/prestaged_manifest.schema.json`` — JSON-schema
    definition of the on-disk format.

Shape of a manifest file (``<dump_stem>.manifest.json`` adjacent to the
``.dump`` file)::

    {
      "source": "mol_raw.chembl",
      "kind": "pg_dump",
      "target_schema": "mol_raw",
      "target_table": "chembl",
      "sha256": "…",
      "row_count": 1_234_567
    }

The loader is intentionally strict on the keys it *consumes* (``row_count``,
``target_schema``, ``target_table``) and tolerant of unknown keys: a richer
schema is allowed to ship alongside the dump without this code needing an
update.

All public entry points never raise — they return ``None`` + log a warning
so missing / malformed manifests degrade to "log and proceed" behavior per
plan.md §B.3.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from dk_data.ingestion.prestaged_types import PrestagedArtifact

# Default tolerance: 0% (strict). Operators can relax via env, but the
# default is "exact match or mismatch" so truncation never slips past
# unless explicitly permitted.
DEFAULT_ROW_TOLERANCE_PCT = 0.0


@dataclass(frozen=True)
class ManifestEntry:
    """One entry parsed from a ``*.manifest.json`` file.

    Only the fields this module *uses* are modeled; the on-disk file may
    contain additional keys (``kind``, ``size_bytes``, ``sha256``, …) —
    those are ignored here and validated elsewhere (e.g. sha256 by the
    existing :func:`compute_sha256` guard).
    """

    target_schema: str
    target_table: str
    expected_row_count: int


def manifest_path_for(artifact: PrestagedArtifact) -> Path:
    """Return the expected manifest path for a ``PrestagedArtifact``.

    The manifest lives next to the dump with stem + ``.manifest.json``
    — i.e. ``chembl.dump`` → ``chembl.manifest.json``. This uses the same
    ``artifact.path`` resolution the loader already does (plan.md §B.3
    hard constraint: no hardcoded paths).
    """
    return artifact.path.with_suffix(".manifest.json")


def load_manifest(artifact: PrestagedArtifact) -> ManifestEntry | None:
    """Load the manifest entry for ``artifact``, or ``None`` if absent.

    Contract (plan.md §B.3):
      - Missing file → return ``None`` + log a warning ("manifest absent,
        row-count gate disabled for this artifact"). Caller must also
        increment ``dk_hydration_manifest_missing_total``.
      - Malformed JSON / missing required keys → return ``None`` + log a
        warning. Treated the same as absent for gating purposes.
      - Present and well-formed → return :class:`ManifestEntry`.

    Never raises.
    """
    path = manifest_path_for(artifact)

    if not path.exists():
        logger.warning(
            "manifest absent, row-count gate disabled for {} "
            "(looked for {})",
            artifact.path.name,
            path.name,
        )
        return None

    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "manifest at {} unreadable ({}); row-count gate disabled",
            path,
            exc,
        )
        return None

    if not isinstance(raw, dict):
        logger.warning(
            "manifest at {} is not a JSON object; row-count gate disabled",
            path,
        )
        return None

    schema = raw.get("target_schema")
    table = raw.get("target_table")
    row_count = raw.get("row_count")

    if not isinstance(schema, str) or not isinstance(table, str):
        logger.warning(
            "manifest at {} missing target_schema/target_table; "
            "row-count gate disabled",
            path,
        )
        return None

    if row_count is None:
        # Explicitly missing expected row_count → treat same as absent.
        # Downstream caller should still emit manifest_missing metric so
        # the gap is visible.
        logger.warning(
            "manifest at {} has no row_count; row-count gate disabled",
            path,
        )
        return None

    if not isinstance(row_count, int) or row_count < 0:
        logger.warning(
            "manifest at {} has invalid row_count={!r}; "
            "row-count gate disabled",
            path,
            row_count,
        )
        return None

    # Belt-and-suspenders: a manifest whose (schema, table) disagrees
    # with the artifact's target would silently gate the wrong table.
    # Refuse to apply it.
    if schema != artifact.target_schema or table != artifact.target_table:
        logger.warning(
            "manifest at {} declares ({},{}) but artifact targets "
            "({},{}); row-count gate disabled",
            path, schema, table,
            artifact.target_schema, artifact.target_table,
        )
        return None

    return ManifestEntry(
        target_schema=schema,
        target_table=table,
        expected_row_count=row_count,
    )


def is_row_count_mismatch(
    expected: int,
    actual: int,
    tolerance_pct: float = DEFAULT_ROW_TOLERANCE_PCT,
) -> bool:
    """Return True iff ``actual`` deviates from ``expected`` beyond ``tolerance_pct``.

    - tolerance_pct=0 (default) → any deviation is a mismatch.
    - tolerance_pct=5 → allow ±5% deviation before flagging.
    - expected=0 is special-cased: actual must also be 0 regardless of
      tolerance (0% of 0 is 0; dividing would be meaningless).
    """
    if expected == 0:
        return actual != 0
    if tolerance_pct <= 0:
        return actual != expected
    allowed = abs(expected) * (tolerance_pct / 100.0)
    return abs(actual - expected) > allowed
