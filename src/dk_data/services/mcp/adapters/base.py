"""BaseAdapter — contract for DB-backed MCP data-tool adapters.

PR #415 / feature 015 introduced `tool_registry.py` and
`tests/test_mcp_adapters.py` that assume every data source has an
`Adapter(BaseAdapter)` exposing `source_name` / `raw_table` /
`raw_schema` / `normalize()`, plus an optional DB-first `db_query()`
short-circuit. That base class was never written — this is it.

`db_query()` contract (load-bearing — see plan §2 H1):
  * return ``None``  -> no local hit; caller falls through to HTTP.
  * return a dict    -> served from the local warehouse (DB-first).
  * RAISE            -> a real error. The caller MUST surface it, not
                        silently treat it as a miss/fallback. A DB
                        outage is not the same as "drug not found".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Abstract base for a data-source adapter.

    Concrete adapters declare which raw warehouse table backs them and
    how to normalize an upstream API response; the registry-driven
    router uses `db_query()` to serve from the warehouse before any
    outbound HTTP call.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Stable source identifier (e.g. ``"clinicaltrials"``)."""

    @property
    @abstractmethod
    def raw_table(self) -> str:
        """Raw landing table name (unqualified, e.g. ``"clinicaltrials"``)."""

    @property
    @abstractmethod
    def raw_schema(self) -> str:
        """Schema holding the raw table (e.g. ``"mol_raw"``)."""

    @abstractmethod
    def normalize(self, api_response: dict) -> dict:
        """Map an upstream API response to the raw-row shape.

        Passthrough is acceptable for sources whose raw layer stores
        the response verbatim.
        """

    # --- concrete contract -------------------------------------------------

    @property
    def full_table_name(self) -> str:
        """Schema-qualified raw table, e.g. ``"mol_raw.clinicaltrials"``."""
        return f"{self.raw_schema}.{self.raw_table}"

    def validate_against_bronze(self, bronze_row: Any | None = None) -> bool:
        """Whether a normalized row is parseable by the bronze model.

        Default ``True`` (FR-025); sources with strict bronze contracts
        override. Accepts an optional row so callers may pass a sample.
        """
        return True

    def build_url(
        self, base_url: str, drug_name: str, params: dict | None = None
    ) -> str:
        """Build the upstream request URL.

        Default appends ``?query=<drug_name>``; HTTP-backed adapters
        override. DB-first adapters that never call out may ignore this.
        """
        return f"{base_url}?query={drug_name}"

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        """Serve from the local warehouse, or ``None`` to fall through.

        Default: no local path (``None`` -> caller does HTTP). Override
        to implement DB-first. Per the module contract, a genuine error
        MUST raise — do not catch-and-return-None, which would make a DB
        outage indistinguishable from a legitimate miss.
        """
        return None
