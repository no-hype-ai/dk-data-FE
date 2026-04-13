"""Company read surface.

Reads from `mol_silver.companies` (hub) and `mol_gold.company_pipeline`.
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class CompaniesModule(ModuleBase):
    async def resolve(self, name: str, *, hint: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name_or_id": name}
        if hint:
            body["hint"] = hint
        return await self._call(
            method="companies.resolve",
            path="/data-platform/companies/resolve",
            args={"name": name, "hint": hint},
            http_method="POST",
            json_body=body,
        )

    async def get(self, company_id: str) -> dict[str, Any]:
        params = {"company_id": f"eq.{company_id}", "limit": "1"}
        rows = await self._call(
            method="companies.get",
            path="/companies",
            args={"id": company_id},
            params=params,
        )
        return dict(rows[0]) if isinstance(rows, list) and rows else {}

    async def get_pipeline(self, company_id: str) -> list[dict[str, Any]]:
        params = {"company_id": f"eq.{company_id}"}
        data = await self._call(
            method="companies.getPipeline",
            path="/company_pipeline",
            args={"id": company_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []
