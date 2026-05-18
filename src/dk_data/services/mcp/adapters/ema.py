"""EMA (European Medicines Agency) MCP adapter.

EMA has no public real-time JSON API.  Data is ingested via the bulk
fetcher pipeline (ema_mol / ema_regulatory / ema_epar) into mol_silver.ema.

This adapter overrides invoke() to serve lookups from mol_silver.ema
via asyncpg instead of hitting a live endpoint.
"""

from typing import Any, List, Optional

from ..base_tool import BaseMCPTool


class EmaTool(BaseMCPTool):
    tool_name = "ema-search"

    db_pool: Any = None

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        if self.db_pool is not None:
            result = await self._db_query(drug_name)
            if result is not None:
                return {
                    "tool": self.tool_name,
                    "error": None,
                    "status_code": 200,
                    "data": result,
                }

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

    async def _db_query(self, drug_name: str) -> Optional[dict]:
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
        async with self.db_pool.acquire() as conn:
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
