"""EMA (European Medicines Agency) MCP adapter.

EMA has no public real-time JSON API.  Data is ingested via the bulk
fetcher pipeline (ema_mol / ema_regulatory / ema_epar) into mol_silver.ema.

This adapter overrides db_query() to serve lookups from mol_silver.ema
instead of hitting a live endpoint.  The HTTP path in BaseMCPTool is never
reached for this source.
"""

from typing import Any, List, Optional

from ..base_tool import BaseMCPTool
from .base import BaseAdapter


class EmaTool(BaseMCPTool):
    tool_name = "ema-search"

    async def invoke(self, _: str) -> dict[str, Any]:
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


class Adapter(BaseAdapter):
    @property
    def source_name(self) -> str:
        return "ema"

    @property
    def raw_table(self) -> str:
        return "ema"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def normalize(self, api_response: dict) -> dict:
        return api_response

    async def db_query(self, drug_name: str, db_pool: Any) -> Optional[dict]:
        """Search mol_silver.ema by active substance, INN, or product name."""
        query = """
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
               OR LOWER(active_substance) LIKE LOWER($1) || '%'
               OR LOWER(inn)              LIKE LOWER($1) || '%'
               OR LOWER(product_name)     LIKE LOWER($1) || '%'
            ORDER BY
                authorization_status = 'Authorised' DESC,
                product_name
            LIMIT 20
        """
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, drug_name)

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
