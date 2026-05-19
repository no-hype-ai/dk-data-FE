"""EMA (European Medicines Agency) MCP adapter.

EMA has no public real-time JSON API.  Data is ingested via the bulk
fetcher pipeline (ema_mol / ema_regulatory / ema_epar) into mol_silver.ema.

Adapter (BaseAdapter): DB-first lookup against mol_silver.ema.
EmaTool (BaseMCPTool): HTTP-fallback — returns the structured "no public API"
  message when the DB layer has no match.  Used by the router's HTTP path.
"""

from typing import Any, List

from ..base_tool import BaseMCPTool
from .base import BaseAdapter

# ---------------------------------------------------------------------------
# Query constant — exposed as module-level so tests can introspect it.
#
# The 6-way OR from the original _db_query is collapsed to 3 sargable
# equality predicates; prefix (LIKE … || '%') expansion is intentionally
# dropped — exact case-insensitive name match only — for index-friendliness
# and to satisfy silver antipattern rules (no LIKE, hence trivially S2-safe;
# no leading wildcard).
#
# Note: this queries the SILVER table mol_silver.ema even though the
# Adapter's raw_schema is "mol_raw" — the raw/silver split is deliberate
# (raw landing vs DB-first serving); see the raw_schema NOTE below.
# ---------------------------------------------------------------------------
_EMA_SILVER_QUERY = """
    SELECT
        product_number,
        product_name,
        active_substance,
        inn,
        atc_code,
        marketing_authorization_holder,
        authorization_status,
        authorization_date::TEXT,
        medicine_type,
        therapeutic_area,
        pharmacotherapeutic_group,
        epar_url,
        summary_url,
        molecule_id::TEXT
    FROM mol_silver.ema
    WHERE LOWER(active_substance) = LOWER($1)
       OR LOWER(inn)              = LOWER($1)
       OR LOWER(product_name)     = LOWER($1)
    ORDER BY
        authorization_status = 'Authorised' DESC,
        product_name
    LIMIT 20
"""


class Adapter(BaseAdapter):
    """DB-first adapter for mol_silver.ema (EMA bulk-fetcher data)."""

    @property
    def source_name(self) -> str:
        return "ema"

    @property
    def raw_table(self) -> str:
        return "ema"

    @property
    def raw_schema(self) -> str:
        # NOTE: raw_schema is the BaseAdapter RAW-landing contract
        # (raw EMA lands in mol_raw.ema; required to stay within
        # {"mol_raw","raw","hcs_raw"} per test_adapter_importable).
        # db_query() deliberately serves DB-first from the SILVER
        # projection mol_silver.ema instead — see _EMA_SILVER_QUERY.
        # Mirrors the openfda_labels.Adapter raw/source split.
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        # EMA has no upstream API; normalize is a passthrough.
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> dict | None:
        """Search mol_silver.ema by active substance, INN, or product name.

        Returns a result dict on hit, None on legitimate miss.
        Propagates any DB exception — callers treat that as a 502, not a miss.
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(_EMA_SILVER_QUERY, drug_name)

        if not rows:
            return None

        results: List[dict] = []
        for r in rows:
            row_dict = dict(r)
            for k, v in row_dict.items():
                if hasattr(v, "isoformat"):
                    row_dict[k] = v.isoformat()
            results.append(row_dict)

        return {"total": len(results), "results": results}


class EmaTool(BaseMCPTool):
    """HTTP-fallback tool for ema-search.

    EMA has no public real-time JSON API.  When the DB layer (Adapter.db_query)
    finds no match, the router falls through to this tool, which returns the
    structured "not supported" response rather than making an outbound HTTP call.
    """

    tool_name = "ema-search"

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        return {
            "tool": self.tool_name,
            "error": (
                "EMA has no free public JSON API. "
                "Data is available via the EMA bulk fetcher pipeline "
                "(fetchers/ema_regulatory.py). "
                "On-demand queries are not supported."
            ),
            "status_code": None,
            "data": None,
        }
