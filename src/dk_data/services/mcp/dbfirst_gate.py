"""DB-first gate — WS4 SP1 (feature 211).

Two env vars, default-off, so the entire DB-first path is inert in
production until a source is explicitly opted in (FR-002 / FR-003):

* ``MCP_DBFIRST_ENABLED`` — global master switch (default false). This is
  the single kill-switch / rollback lever (FR-007).
* ``MCP_DBFIRST_SOURCES`` — comma-separated allowlist of router slugs.

An unknown / misspelled slug in the list is simply inert (it never
matches a real slug), which is the intended edge-case behaviour.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def dbfirst_enabled() -> bool:
    """Global master switch (default ``False``)."""
    return os.getenv("MCP_DBFIRST_ENABLED", "").strip().lower() in _TRUE


def dbfirst_sources() -> set[str]:
    """Per-source allowlist (router slugs); empty by default."""
    return {
        s.strip()
        for s in os.getenv("MCP_DBFIRST_SOURCES", "").split(",")
        if s.strip()
    }


def gate_on(slug: str) -> bool:
    """DB-first is active for *slug* iff the master switch is on AND the
    slug is allow-listed."""
    return dbfirst_enabled() and slug in dbfirst_sources()
