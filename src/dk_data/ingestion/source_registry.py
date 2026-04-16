"""Source descriptor loader + meta.source_registry sync.

Feature: Horizon 3 / plan §D.2 — declarative source descriptors.

What this module does
---------------------
Walks ``.dk/sources/*.yaml`` descriptors (schema: ``.dk/sources/_schema.yaml``),
validates them, and upserts rows into ``meta.source_registry`` (migration 233)
so every consumer of source metadata (CLI `dk data source list`, the
§D.1 dispatcher, observability dashboards, §D.3 admission controller)
reads from one place.

Public API
----------
- :class:`SourceDescriptor`        — frozen dataclass, one-per-YAML file.
- :func:`load_descriptor`          — load + validate a single file.
- :func:`load_all`                 — walk a directory and load every ``*.yaml``
  other than ``_schema.yaml``.
- :func:`sync_to_db`               — upsert a list of descriptors into
  ``meta.source_registry`` via the sanctioned connection pool (FR-030).

CLI
---
``python -m dk_data.ingestion.source_registry --sync``
    Load every descriptor and upsert into the DB.

``python -m dk_data.ingestion.source_registry --list [--tier N]``
    Print the rows currently in the DB as a small table.

FR-030 compliance
-----------------
Every DB connection is leased from ``get_connection_pool()``. Raw
connection construction outside database.py is forbidden. Mirrors the
pattern in ``hydration_backlog.py``. The T003 CI grep gate fails any
diff that imports the raw connect API directly outside
``ingestion/utils/database.py``.

Validation
----------
The descriptor schema is embedded in ``.dk/sources/_schema.yaml`` under
``json_schema:``. We do not add a new ``jsonschema`` dependency for this
module — the validator is hand-rolled against the Draft-2020-12 subset
actually used (type, enum, pattern, required, minimum, maximum,
additionalProperties, minLength, uniqueItems). This keeps the tree's
declared deps unchanged (see pyproject.toml) and matches the lightweight
validation pattern already used by ``prestaged_manifest.py``.

Kind-specific requireds (enforced after schema validation):
    postgres_dump       → fetch.artifact_uri
    http_csv            → fetch.url
    http_json_paginated → fetch.url
    zip                 → fetch.url
    api_key             → fetch.url + credentials_ref != 'none'
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import psycopg2
import psycopg2.extras
import yaml

from dk_data.ingestion.utils.database import (
    get_connection_pool,
    init_connection_pool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
VALID_DOMAINS = frozenset({"mol", "hcs", "hcp", "ind", "ip", "dev"})
VALID_KINDS = frozenset(
    {"postgres_dump", "http_csv", "http_json_paginated", "zip", "api_key"}
)
VALID_STATUSES = frozenset({"stub", "fetcher_ready", "live"})

# Fields that every descriptor must carry.
REQUIRED_FIELDS: Tuple[str, ...] = (
    "name",
    "domain",
    "tier",
    "depends_on",
    "fetch",
    "schedule",
    "credentials_ref",
    "sla_seconds",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DescriptorValidationError(ValueError):
    """Raised when a descriptor fails schema validation.

    Carries the source path (if known) and the offending field so the CLI
    can point the operator at the right line.
    """

    def __init__(self, message: str, *, path: Optional[Path] = None, field_name: Optional[str] = None) -> None:
        self.path = path
        self.field_name = field_name
        prefix = f"{path}: " if path else ""
        if field_name:
            prefix += f"[{field_name}] "
        super().__init__(prefix + message)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceDescriptor:
    """Validated, in-memory representation of one ``.dk/sources/<name>.yaml``.

    Frozen so two identical descriptors compare equal (used by the
    round-trip test) and so upstream callers can't mutate the loaded
    spec after validation.
    """

    name: str
    domain: str
    tier: int
    depends_on: Tuple[str, ...]
    fetch: Mapping[str, Any]
    schedule: str
    credentials_ref: str
    sla_seconds: int
    expected_row_count_fn: Optional[str] = None
    manifest: Optional[str] = None
    consumes: Mapping[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a plain dict (YAML-ready). Deterministic order."""
        out: Dict[str, Any] = {
            "name": self.name,
            "domain": self.domain,
            "tier": self.tier,
            "depends_on": list(self.depends_on),
            "fetch": dict(self.fetch),
            "schedule": self.schedule,
            "credentials_ref": self.credentials_ref,
            "sla_seconds": self.sla_seconds,
        }
        if self.expected_row_count_fn is not None:
            out["expected_row_count_fn"] = self.expected_row_count_fn
        if self.manifest is not None:
            out["manifest"] = self.manifest
        if self.consumes:
            out["consumes"] = dict(self.consumes)
        return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _require(data: Mapping[str, Any], key: str, *, path: Optional[Path]) -> Any:
    """Return ``data[key]`` or raise ``DescriptorValidationError``."""
    if key not in data:
        raise DescriptorValidationError(
            f"missing required field '{key}'", path=path, field_name=key
        )
    return data[key]


def _validate(data: Mapping[str, Any], *, path: Optional[Path]) -> None:
    """Hand-rolled validation against the embedded JSON-Schema subset.

    Covers: required fields, enums, name regex, tier range, SLA range,
    depends_on uniqueness, fetch.kind + kind-specific requireds,
    unknown-field detection.
    """
    if not isinstance(data, Mapping):
        raise DescriptorValidationError(
            "descriptor root must be a mapping", path=path
        )

    # Unknown fields at the root level.
    allowed = set(REQUIRED_FIELDS) | {"expected_row_count_fn", "manifest", "consumes"}
    unknown = set(data.keys()) - allowed
    if unknown:
        raise DescriptorValidationError(
            f"unknown field(s) at root: {sorted(unknown)!r}",
            path=path,
        )

    for key in REQUIRED_FIELDS:
        _require(data, key, path=path)

    # name
    name = data["name"]
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise DescriptorValidationError(
            f"name must match {NAME_PATTERN.pattern!r}; got {name!r}",
            path=path,
            field_name="name",
        )

    # domain
    if data["domain"] not in VALID_DOMAINS:
        raise DescriptorValidationError(
            f"domain must be one of {sorted(VALID_DOMAINS)!r}; got {data['domain']!r}",
            path=path,
            field_name="domain",
        )

    # tier
    tier = data["tier"]
    if not isinstance(tier, int) or isinstance(tier, bool) or not (1 <= tier <= 8):
        raise DescriptorValidationError(
            f"tier must be an integer in [1, 8]; got {tier!r}",
            path=path,
            field_name="tier",
        )

    # depends_on: list[str], each matching the name pattern, unique
    deps = data["depends_on"]
    if not isinstance(deps, list):
        raise DescriptorValidationError(
            "depends_on must be a list", path=path, field_name="depends_on"
        )
    if len(set(deps)) != len(deps):
        raise DescriptorValidationError(
            "depends_on entries must be unique", path=path, field_name="depends_on"
        )
    for dep in deps:
        if not isinstance(dep, str) or not NAME_PATTERN.match(dep):
            raise DescriptorValidationError(
                f"depends_on entry {dep!r} must match {NAME_PATTERN.pattern!r}",
                path=path,
                field_name="depends_on",
            )

    # fetch.kind + kind-specific requireds
    fetch = data["fetch"]
    if not isinstance(fetch, Mapping):
        raise DescriptorValidationError(
            "fetch must be a mapping", path=path, field_name="fetch"
        )
    kind = fetch.get("kind")
    if kind not in VALID_KINDS:
        raise DescriptorValidationError(
            f"fetch.kind must be one of {sorted(VALID_KINDS)!r}; got {kind!r}",
            path=path,
            field_name="fetch.kind",
        )
    if kind == "postgres_dump":
        if not fetch.get("artifact_uri"):
            raise DescriptorValidationError(
                "fetch.artifact_uri is required for kind=postgres_dump",
                path=path,
                field_name="fetch.artifact_uri",
            )
    elif kind in ("http_csv", "http_json_paginated", "zip"):
        if not fetch.get("url"):
            raise DescriptorValidationError(
                f"fetch.url is required for kind={kind}",
                path=path,
                field_name="fetch.url",
            )
    elif kind == "api_key":
        if not fetch.get("url"):
            raise DescriptorValidationError(
                "fetch.url is required for kind=api_key",
                path=path,
                field_name="fetch.url",
            )
        if data.get("credentials_ref", "none") == "none":
            raise DescriptorValidationError(
                "credentials_ref cannot be 'none' for kind=api_key",
                path=path,
                field_name="credentials_ref",
            )

    # schedule / credentials_ref: non-empty strings
    for str_field in ("schedule", "credentials_ref"):
        val = data[str_field]
        if not isinstance(val, str) or not val.strip():
            raise DescriptorValidationError(
                f"{str_field} must be a non-empty string",
                path=path,
                field_name=str_field,
            )

    # sla_seconds
    sla = data["sla_seconds"]
    if not isinstance(sla, int) or isinstance(sla, bool) or not (1 <= sla <= 604800):
        raise DescriptorValidationError(
            f"sla_seconds must be an integer in [1, 604800]; got {sla!r}",
            path=path,
            field_name="sla_seconds",
        )

    # Optional: consumes must be a mapping if present.
    if "consumes" in data and not isinstance(data["consumes"], Mapping):
        raise DescriptorValidationError(
            "consumes must be a mapping when present",
            path=path,
            field_name="consumes",
        )

    # Optional strings: allow null (YAML → None) so callers can keep the
    # key for documentation while punting the actual value. Reject any
    # non-string, non-None value.
    for opt_str in ("expected_row_count_fn", "manifest"):
        if opt_str in data and data[opt_str] is not None and not isinstance(data[opt_str], str):
            raise DescriptorValidationError(
                f"{opt_str} must be a string or null",
                path=path,
                field_name=opt_str,
            )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_descriptor(path: Path) -> SourceDescriptor:
    """Load and validate a single descriptor YAML file.

    Args:
        path: Absolute or repo-relative path to a ``.yaml`` file.

    Returns:
        A :class:`SourceDescriptor`.

    Raises:
        FileNotFoundError: path doesn't exist.
        DescriptorValidationError: schema check failed.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Descriptor not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    _validate(raw, path=path)

    # Filename must match the name field (operators can otherwise rename
    # and desync the PK). The schema file itself is skipped by load_all.
    expected_stem = raw["name"]
    if path.stem != expected_stem:
        raise DescriptorValidationError(
            f"filename stem {path.stem!r} must match name {expected_stem!r}",
            path=path,
            field_name="name",
        )

    return SourceDescriptor(
        name=raw["name"],
        domain=raw["domain"],
        tier=int(raw["tier"]),
        depends_on=tuple(raw["depends_on"]),
        fetch=dict(raw["fetch"]),
        schedule=raw["schedule"],
        credentials_ref=raw["credentials_ref"],
        sla_seconds=int(raw["sla_seconds"]),
        expected_row_count_fn=raw.get("expected_row_count_fn"),
        manifest=raw.get("manifest"),
        consumes=dict(raw.get("consumes") or {}),
    )


def load_all(root: Path) -> List[SourceDescriptor]:
    """Walk ``root`` and load every ``*.yaml`` other than ``_schema.yaml``.

    Names starting with ``_`` are treated as reserved (the v1 schema file
    is ``_schema.yaml``). Files are sorted for deterministic output.
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Descriptor root not found: {root}")

    descriptors: List[SourceDescriptor] = []
    for entry in sorted(root.glob("*.yaml")):
        if entry.name.startswith("_"):
            continue
        descriptors.append(load_descriptor(entry))
    return descriptors


# ---------------------------------------------------------------------------
# DB sync
# ---------------------------------------------------------------------------


_UPSERT_SQL = """
INSERT INTO meta.source_registry (
    name, domain, tier, depends_on, "fetch", schedule,
    credentials_ref, expected_row_count_sql, sla_seconds,
    manifest_path, consumes, updated_at
)
VALUES (
    %(name)s, %(domain)s, %(tier)s, %(depends_on)s::jsonb, %(fetch)s::jsonb, %(schedule)s,
    %(credentials_ref)s, %(expected_row_count_sql)s, %(sla_seconds)s,
    %(manifest_path)s, %(consumes)s::jsonb, NOW()
)
ON CONFLICT (name) DO UPDATE SET
    domain                 = EXCLUDED.domain,
    tier                   = EXCLUDED.tier,
    depends_on             = EXCLUDED.depends_on,
    "fetch"                = EXCLUDED."fetch",
    schedule               = EXCLUDED.schedule,
    credentials_ref        = EXCLUDED.credentials_ref,
    expected_row_count_sql = EXCLUDED.expected_row_count_sql,
    sla_seconds            = EXCLUDED.sla_seconds,
    manifest_path          = EXCLUDED.manifest_path,
    consumes               = EXCLUDED.consumes,
    updated_at             = NOW()
RETURNING (xmax = 0) AS inserted;
"""


def _params_for(descriptor: SourceDescriptor) -> Dict[str, Any]:
    """Translate a descriptor into the upsert parameter dict."""
    return {
        "name": descriptor.name,
        "domain": descriptor.domain,
        "tier": descriptor.tier,
        "depends_on": json.dumps(list(descriptor.depends_on)),
        "fetch": json.dumps(dict(descriptor.fetch)),
        "schedule": descriptor.schedule,
        "credentials_ref": descriptor.credentials_ref,
        "expected_row_count_sql": descriptor.expected_row_count_fn,
        "sla_seconds": descriptor.sla_seconds,
        "manifest_path": descriptor.manifest,
        "consumes": json.dumps(dict(descriptor.consumes)),
    }


def sync_to_db(
    descriptors: Sequence[SourceDescriptor],
    conn: Optional[psycopg2.extensions.connection] = None,
) -> Dict[str, int]:
    """Upsert descriptors into ``meta.source_registry``.

    FR-030: connection leased from ``get_connection_pool()`` when ``conn``
    is None — never constructs a raw psycopg2 connection.

    Args:
        descriptors: sequence of validated descriptors.
        conn: optional pre-built connection. When ``None``, one is leased
            from the pool, used in autocommit mode, and returned.

    Returns:
        ``{"inserted": N, "updated": M, "total": N+M}``.
    """
    inserted = 0
    updated = 0

    owns_conn = False
    if conn is None:
        try:
            pool = get_connection_pool()
        except RuntimeError:
            init_connection_pool()
            pool = get_connection_pool()
        conn = pool.getconn()
        conn.autocommit = True
        owns_conn = True

    try:
        with conn.cursor() as cur:
            for descriptor in descriptors:
                cur.execute(_UPSERT_SQL, _params_for(descriptor))
                row = cur.fetchone()
                was_inserted = bool(row and row[0])
                if was_inserted:
                    inserted += 1
                else:
                    updated += 1
    finally:
        if owns_conn:
            try:
                get_connection_pool().putconn(conn)
            except Exception:  # pragma: no cover — defensive
                pass

    total = inserted + updated
    logger.info(
        "source_registry sync complete: inserted=%d updated=%d total=%d",
        inserted,
        updated,
        total,
    )
    return {"inserted": inserted, "updated": updated, "total": total}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _default_sources_root() -> Path:
    """Resolve the default sources root.

    Precedence: ``DK_SOURCES_ROOT`` env var, else ``<repo>/.dk/sources``
    relative to this file.
    """
    env = os.environ.get("DK_SOURCES_ROOT")
    if env:
        return Path(env)
    # src/dk_data/ingestion/source_registry.py → repo root is 3 parents up
    return Path(__file__).resolve().parents[3] / ".dk" / "sources"


def _cmd_sync(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else _default_sources_root()
    descriptors = load_all(root)
    if not descriptors:
        logger.warning("No descriptors found under %s", root)
        return 0
    summary = sync_to_db(descriptors)
    print(json.dumps(summary))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    """List rows from ``meta.source_registry``, optionally filtered by tier."""
    try:
        pool = get_connection_pool()
    except RuntimeError:
        init_connection_pool()
        pool = get_connection_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if args.tier is not None:
                cur.execute(
                    """
                    SELECT name, domain, tier, status, schedule, sla_seconds, updated_at
                      FROM meta.source_registry
                     WHERE tier = %s
                     ORDER BY domain, name
                    """,
                    (args.tier,),
                )
            else:
                cur.execute(
                    """
                    SELECT name, domain, tier, status, schedule, sla_seconds, updated_at
                      FROM meta.source_registry
                     ORDER BY tier, domain, name
                    """
                )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        pool.putconn(conn)

    # Small human-readable table. Machine consumers should query the DB
    # directly (PostgREST will expose meta.source_registry when wired).
    if not rows:
        print("(no rows)")
        return 0
    headers = ["name", "domain", "tier", "status", "schedule", "sla_seconds"]
    widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
    line = "  ".join(h.ljust(widths[h]) for h in headers)
    print(line)
    print("  ".join("-" * widths[h] for h in headers))
    for r in rows:
        print("  ".join(str(r[h]).ljust(widths[h]) for h in headers))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dk_data.ingestion.source_registry",
        description="Source descriptor loader + meta.source_registry sync.",
    )
    parser.add_argument(
        "--root",
        help="Override the sources root (default: $DK_SOURCES_ROOT or "
        "<repo>/.dk/sources).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sync", action="store_true", help="Upsert descriptors into meta.source_registry.")
    mode.add_argument("--list", action="store_true", help="List rows from meta.source_registry.")
    parser.add_argument("--tier", type=int, help="Filter --list by tier.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.sync:
        return _cmd_sync(args)
    return _cmd_list(args)


__all__ = [
    "SourceDescriptor",
    "DescriptorValidationError",
    "load_descriptor",
    "load_all",
    "sync_to_db",
    "NAME_PATTERN",
    "VALID_DOMAINS",
    "VALID_KINDS",
]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
