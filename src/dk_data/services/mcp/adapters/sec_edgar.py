"""MCP Adapter: sec_edgar

Feature: 019-cms-puf-platform-reconciliation (rewrite)

Fixes from original:
  - URL was malformed: base_url already contained ?q= so appending ?q= again
    produced a double-query-string.  Now always constructs URLs from scratch.
  - Full-text drug-name search on secsearch.sec.gov returns nothing for INN
    names.  Primary strategy is now ?entity= search against the manufacturer /
    SEC company names from DrugResolution; full-text search is the fallback.
"""

from typing import Any, List
from urllib.parse import quote

from .base import BaseAdapter

# EDGAR full-text search index endpoint (no ?q= in the base — built here)
_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
_DATE_FILTER = "&forms=10-K,10-Q,8-K&dateRange=custom&startdt=2020-01-01"


_SEC_EDGAR_DB_QUERY = """
    SELECT response_body
    FROM mol_raw.sec_edgar
    WHERE response_body::text ILIKE '%' || $1 || '%'
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """Adapter for SEC EDGAR full-text search API responses."""

    @property
    def source_name(self) -> str:
        return "sec_edgar"

    @property
    def raw_table(self) -> str:
        return "sec_edgar"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    # ------------------------------------------------------------------
    # URL builders
    # ------------------------------------------------------------------

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Fallback: full-text search for the drug name (low precision)."""
        return (
            f"{_EDGAR_SEARCH}"
            f'?q="{quote(drug_name)}"'
            f"{_DATE_FILTER}"
        )

    def build_urls_with_resolution(
        self, base_url: str, resolution: Any, params: dict
    ) -> List[str]:
        """Return ordered URLs for resolution-aware EDGAR search.

        Strategy:
          1. Full-text search for the canonical drug name — EDGAR EFTS indexes
             the full content of 10-K/10-Q/8-K filings, so drug names that
             appear in filings are found reliably (517 hits for "dupilumab").
          2. Full-text search for each brand name (up to 2).
          3. Full-text search for manufacturer name (contextual filings).

        Note: entity= parameter on efts.sec.gov does NOT filter by company
        name — it behaves as full-text and returns irrelevant results.
        Use q= (full-text) throughout.
        """
        urls: List[str] = []
        seen: set = set()

        def _add(url: str) -> None:
            if url not in seen:
                seen.add(url)
                urls.append(url)

        # 1. Full-text search on canonical drug name (most direct)
        _add(
            f"{_EDGAR_SEARCH}"
            f'?q="{quote(resolution.canonical_name)}"'
            f"{_DATE_FILTER}"
        )

        # 2. Full-text search on brand names (some filings use only brand name)
        for brand in resolution.brand_names[:2]:
            _add(
                f"{_EDGAR_SEARCH}"
                f'?q="{quote(brand)}"'
                f"{_DATE_FILTER}"
            )

        # 3. Manufacturer name — finds company's own filings that discuss the drug
        for company in resolution.edgar_search_terms()[:2]:
            _add(
                f"{_EDGAR_SEARCH}"
                f'?q="{quote(company)}"'
                f"&forms=10-K,20-F"
                f"&dateRange=custom&startdt=2020-01-01"
            )

        # Always have at least the fallback
        if not urls:
            _add(self.build_url(base_url, resolution.query_name, params))

        return urls

    # ------------------------------------------------------------------
    # Normalizer
    # ------------------------------------------------------------------

    def normalize(self, api_response: dict) -> dict:
        """Pass through the raw EDGAR response unchanged."""
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_SEC_EDGAR_DB_QUERY, drug_name)
        if not rows:
            return None
        return {"source": "sec_edgar_local", "results": [dict(r) for r in rows]}
