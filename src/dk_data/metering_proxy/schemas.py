"""Schema-level access control for the metering proxy.

Inspects the PostgREST URL path to determine the target schema
and enforces consumer access control based on the allowed_schemas
list in the consumer's configuration.

PostgREST URL format: /{schema}/{table}?query
Default schema (no prefix): uses PGRST_DB_SCHEMAS first schema.
"""

import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Known PostgREST schemas in dk-data.
#
# Adding a new schema here is REQUIRED before a consumer's
# `allowed_schemas` entry in consumers.yaml will actually work — an
# unrecognized first path segment falls through to the `api` default,
# silently bypassing the per-schema allowlist.
KNOWN_SCHEMAS = {
    # Molecule domain
    "mol_raw",
    "mol_bronze",
    "mol_silver",
    "mol_gold",
    "mol_api",
    # HCS domain
    "hcs_raw",
    "hcs_bronze",
    "hcs_silver",
    "hcs_gold",
    # Indicator / condition domain
    "ind_raw",
    "ind_bronze",
    "ind_silver",
    "ind_gold",
    # HCP domain
    "hcp_silver",
    "hcp_gold",
    # IP (Intellectual Property) domain — patents, trademarks, designs
    "ip_raw",
    "ip_bronze",
    "ip_silver",
    "ip_gold",
    "ip_api",
    # Cross-domain carve-outs (see CLAUDE.md — the only unprefixed
    # schemas allowed in dk-data)
    "api",
    "mart",
    "scoring",
    "targeting",
    "meta",
    "staging",
    "xenon",
    "application",
    # Agents schemas (US-18 — `agents` is canonical; `mol_agents` /
    # `hcs_agents` are deprecated but still in production for now)
    "agents",
    "mol_agents",
    "hcs_agents",
    # Legacy bare names (no longer used in production; kept for compat)
    "bronze",
    "silver",
    "gold",
    "raw",
}

# Paths that bypass schema checks (health, metrics, OpenAPI spec)
BYPASS_PATHS = {"/health", "/metrics", "/ready", "/"}

# PostgREST OpenAPI spec path
OPENAPI_PATH_PATTERN = re.compile(r"^/?$")


def extract_schema_from_path(
    path: str, profile: Optional[str] = None
) -> Optional[str]:
    """Extract the target schema for a PostgREST request.

    Precedence (operator decision 2026-05-17, Option 1 — Accept-Profile
    pass-through): an explicit PostgREST profile header wins over the
    URL path segment, which in turn wins over the ``api`` default:

        explicit profile header > path segment > ``api`` default

    PostgREST uses ``Accept-Profile`` (reads) / ``Content-Profile``
    (writes) to choose the schema it serves from, and proxy.py forwards
    that header untouched. Authorizing against the path alone meant a
    bare path like ``/tavr_program_year`` fell through to ``api`` and a
    consumer entitled to ``hcs_gold`` (but not ``api``) was wrongly
    denied. Honoring the profile makes the schema we authorize against
    the same schema PostgREST will actually serve.

    The profile is only honored when it names a *known* schema. An
    unrecognized profile falls through to path/default so a bogus
    header cannot widen access — and PostgREST itself rejects unknown
    profiles, so the fallback stays consistent with what it serves.

    Args:
        path: The URL path (e.g., '/mart/drugs' or '/drugs').
        profile: The Accept-Profile / Content-Profile header value, if
            the client sent one. None or empty means "no profile".

    Returns:
        The schema name, or None if the path should bypass checks.
    """
    if path in BYPASS_PATHS:
        return None

    # Explicit profile header wins — but only if it names a schema we
    # recognize (an unrecognized value must not become the auth target).
    if profile:
        profile_schema = profile.strip().lower()
        if profile_schema in KNOWN_SCHEMAS:
            return profile_schema

    # Strip leading slash and split
    parts = path.strip("/").split("/")
    if not parts or not parts[0]:
        return None

    first_segment = parts[0].lower()

    # Check if it matches a known schema
    if first_segment in KNOWN_SCHEMAS:
        return first_segment

    # Default schema — the request goes to the first schema in PGRST_DB_SCHEMAS
    return "api"


def check_schema_access(
    consumer_alias: str,
    allowed_schemas: list[str],
    target_schema: str,
) -> bool:
    """Check if a consumer is allowed to access a schema.

    Args:
        consumer_alias: The consumer's alias for logging.
        allowed_schemas: List of schemas the consumer can access.
                         ["*"] means all schemas.
        target_schema: The schema being accessed.

    Returns:
        True if access is allowed, False otherwise.
    """
    # Wildcard allows all schemas
    if "*" in allowed_schemas:
        return True

    if target_schema in allowed_schemas:
        return True

    logger.warning(
        "schema_access_denied",
        consumer=consumer_alias,
        schema=target_schema,
        allowed=allowed_schemas,
    )
    return False
