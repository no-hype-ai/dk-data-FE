"""Healthcare provider read surface.

Reads from `hcs_silver.providers` via the FastAPI resolve wrapper.
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class ProvidersModule(ModuleBase):
    async def resolve(self, npi_or_name: str, *, hint: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name_or_id": npi_or_name}
        if hint:
            body["hint"] = hint
        return await self._call(
            method="providers.resolve",
            path="/data-platform/providers/resolve",
            args={"npi_or_name": npi_or_name, "hint": hint},
            http_method="POST",
            json_body=body,
        )

    async def get(self, provider_id: str) -> dict[str, Any]:
        params = {"provider_id": f"eq.{provider_id}", "limit": "1"}
        rows = await self._call(
            method="providers.get",
            path="/providers",
            args={"id": provider_id},
            params=params,
        )
        return dict(rows[0]) if isinstance(rows, list) and rows else {}
