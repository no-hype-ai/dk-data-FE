"""Patents / IP read surface.

Reads from `ip_silver.patents` (unified hub — USPTO + EPO + EUIPO).
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class PatentsModule(ModuleBase):
    async def search(
        self,
        *,
        query: str | None = None,
        assignee: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "select": "patent_id,title,assignee,filing_date,publication_date,jurisdiction",
            "limit": str(limit),
            "order": "filing_date.desc",
        }
        if query:
            params["title"] = f"ilike.*{query}*"
        if assignee:
            params["assignee"] = f"ilike.*{assignee}*"
        data = await self._call(
            method="patents.search",
            path="/patents",
            args={"query": query, "assignee": assignee, "limit": limit},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_by_molecule(self, molecule_id: str) -> list[dict[str, Any]]:
        params = {
            "molecule_id": f"eq.{molecule_id}",
            "order": "filing_date.desc",
            "limit": "100",
        }
        data = await self._call(
            method="patents.getByMolecule",
            path="/patents",
            args={"molecule_id": molecule_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []
