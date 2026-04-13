"""Shared base class for domain modules.

Every module receives the client by reference and delegates calls
through `client.call()`. This module exists to carry that one-line
pattern without duplicating it across six modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dk_data_client.client import DkDataClient


class ModuleBase:
    """Every domain module inherits this — just holds a client ref."""

    def __init__(self, client: DkDataClient) -> None:
        self._client = client

    async def _call(
        self,
        *,
        method: str,
        path: str,
        args: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        http_method: str = "GET",
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        return await self._client.call(
            method=method,
            path=path,
            args=args or {},
            params=params,
            http_method=http_method,
            json_body=json_body,
        )
