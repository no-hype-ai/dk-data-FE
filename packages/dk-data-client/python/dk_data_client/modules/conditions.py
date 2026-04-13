"""Condition / indication read surface.

Reads from `ind_silver.conditions` and uses the FastAPI
`/data-platform/conditions/resolve` wrapper.
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class ConditionsModule(ModuleBase):
    async def resolve(self, name_or_code: str, *, hint: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name_or_id": name_or_code}
        if hint:
            body["hint"] = hint
        return await self._call(
            method="conditions.resolve",
            path="/data-platform/conditions/resolve",
            args={"name_or_code": name_or_code, "hint": hint},
            http_method="POST",
            json_body=body,
        )

    async def search(self, query: str, *, limit: int = 25) -> list[dict[str, Any]]:
        params = {
            "select": "condition_id,canonical_name,icd10,mesh",
            "canonical_name": f"ilike.*{query}*",
            "limit": str(limit),
        }
        data = await self._call(
            method="conditions.search",
            path="/conditions",
            args={"query": query, "limit": limit},
            params=params,
        )
        return list(data) if isinstance(data, list) else []
