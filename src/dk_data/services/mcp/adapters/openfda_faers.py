"""MCP Adapter: openfda_faers

Feature: 019-cms-puf-platform-reconciliation (rewrite)

Fixes from original:
  - Searched only generic_name field.  Brand-name submissions in FAERS were
    missed entirely.
  - No fallback when generic_name search returns empty.

Now uses build_urls_with_resolution() to generate an ordered list of
field-qualified URLs (generic_name, substance_name, brand_name) for all
known name forms from the DrugResolution, so any FAERS submission format
will be found.
"""

from typing import Any, List
from urllib.parse import quote

from .base import BaseAdapter

_FAERS_URL = "https://api.fda.gov/drug/event.json"


class Adapter(BaseAdapter):
    """Adapter for OpenFDA drug/event (FAERS) API."""

    @property
    def source_name(self) -> str:
        return "openfda_faers"

    @property
    def raw_table(self) -> str:
        return "openfda_faers"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    # ------------------------------------------------------------------
    # URL builders
    # ------------------------------------------------------------------

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Default: search by generic_name (used when no resolution is available)."""
        return (
            f"{_FAERS_URL}"
            f'?search=patient.drug.openfda.generic_name:"{quote(drug_name)}"'
            f"&limit=10"
        )

    def build_urls_with_resolution(
        self, base_url: str, resolution: Any, params: dict
    ) -> List[str]:
        """Return ordered FAERS URLs covering all known name forms.

        Tries the following field × name combinations, deduped:
          - generic_name  for canonical_name
          - substance_name for canonical_name
          - brand_name    for each brand name
          - generic_name  for each brand name (sometimes filed as generic in FAERS)
          - generic_name / brand_name for original query_name if different
        """
        urls: List[str] = []
        seen: set = set()

        def _add(field: str, name: str) -> None:
            url = (
                f"{_FAERS_URL}"
                f'?search=patient.drug.openfda.{field}:"{quote(name)}"'
                f"&limit=10"
            )
            if url not in seen:
                seen.add(url)
                urls.append(url)

        # Canonical name across primary FAERS fields
        _add("generic_name", resolution.canonical_name)
        _add("substance_name", resolution.canonical_name)

        # Each brand name
        for brand in resolution.brand_names:
            _add("brand_name", brand)
            _add("generic_name", brand)  # brand sometimes filed as generic in FAERS

        # Original query name if it differs from canonical
        if resolution.query_name.lower() != resolution.canonical_name.lower():
            _add("generic_name", resolution.query_name)
            _add("brand_name", resolution.query_name)

        # Always provide at least the basic fallback
        if not urls:
            urls.append(self.build_url(base_url, resolution.query_name, params))

        return urls

    # ------------------------------------------------------------------
    # Normalizer
    # ------------------------------------------------------------------

    def normalize(self, api_response: dict) -> dict:
        """Pass through the raw FAERS response unchanged."""
        return api_response
