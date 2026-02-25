"""Base adapter class for MCP data retrieval tools.

Feature: 015-assessment-dashboard-integration
Task: T059

Each adapter normalizes external API responses to the canonical
response_body JSONB format expected by its corresponding bronze model.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


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
