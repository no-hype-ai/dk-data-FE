"""Base adapter class for MCP data retrieval tools.

Feature: 015-assessment-dashboard-integration
Task: T059

Each adapter normalizes external API responses to the canonical
response_body JSONB format expected by its corresponding bronze model.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional  # noqa: F401


class BaseAdapter(ABC):
    """Abstract base class for MCP source adapters.

    Subclasses must implement:
    - normalize(api_response) → dict matching bronze model response_body schema
    - source_name property → identifies the external data source
    - raw_table property → target raw table name (e.g., 'clinicaltrials')
    - raw_schema property → 'mol_raw' or 'raw'
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this data source (e.g., 'clinicaltrials', 'pubmed')."""
        ...

    @property
    @abstractmethod
    def raw_table(self) -> str:
        """Target raw table name without schema prefix (e.g., 'clinicaltrials')."""
        ...

    @property
    @abstractmethod
    def raw_schema(self) -> str:
        """Target raw schema: 'mol_raw' for molecule-specific, 'raw' for IP/regulatory."""
        ...

    @abstractmethod
    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to canonical response_body JSONB format.

        Args:
            api_response: Raw response from the external API.

        Returns:
            Dict matching the response_body schema expected by the
            corresponding bronze SQLMesh model.
        """
        ...

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Build the API URL for this source. Override per-adapter for custom URL logic.

        Default appends ?query={drug_name} which works for some APIs.
        """
        return f"{base_url}?query={drug_name}"

    def build_urls_with_resolution(self, base_url: str, resolution: Any, params: dict) -> list:
        """Return an ordered list of URLs to try, using resolved drug name forms.

        Default implementation returns a single URL built from the canonical name.
        Override in adapters that benefit from trying multiple aliases or
        resolution-derived search strategies (e.g. sec_edgar, openfda_faers).

        Args:
            base_url: The tool's configured API base URL.
            resolution: A DrugResolution instance from DrugResolver.
            params: Raw input_params dict from the invoke call.

        Returns:
            Ordered list of URL strings.  BaseMCPTool tries each in sequence,
            stopping at the first that returns non-empty results.
        """
        return [self.build_url(base_url, resolution.canonical_name, params)]

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Validate that normalized data has required fields for the bronze model.

        Default implementation returns True. Override in subclasses that need
        stricter validation.

        Args:
            normalized: Output from normalize().

        Returns:
            True if the normalized data is valid for the bronze model.
        """
        return True

    @property
    def full_table_name(self) -> str:
        """Full qualified table name (schema.table)."""
        return f"{self.raw_schema}.{self.raw_table}"

    async def db_query(self, drug_name: str, db_pool: Any) -> Optional[dict]:
        """Serve from the local warehouse, or ``None`` to fall through (H1).

        Contract (load-bearing — WS4 SP1 / FR-001 / FR-004):
          * return ``None``  -> no local hit; caller falls through to the
            existing HTTP path.
          * return a non-empty dict -> served from the warehouse (DB-first).
          * RAISE -> a real error. The caller MUST surface it (502), not
            silently treat it as a miss. A DB outage is not "not found";
            do NOT catch-and-return-None.

        Default: no DB path (``None``). Adapters override to implement
        DB-first. Adding this method is additive — it does not change any
        existing feature-015 adapter behaviour.
        """
        return None
