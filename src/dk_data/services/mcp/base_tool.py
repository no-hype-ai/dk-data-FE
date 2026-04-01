"""Base MCP data-tool adapter.

Fixes applied (issue #188):
  B1 - follow_redirects=True (was False, broke TTD and others)
  B2 - Accept: application/json default header (was absent, ORCID returned XML)
  B3 - Content-Type check before response.json() (was unconditional, caused JSONDecodeError)
"""

from __future__ import annotations

from abc import ABC
from typing import Any

import httpx


class BaseMCPTool(ABC):
    """Abstract base for all MCP data-tool adapters."""

    tool_name: str = ""
    base_url: str = ""

    def build_url(self, drug_name: str) -> str:
        """Build the upstream request URL.

        Default pattern is ``?query={drug_name}``.
        Subclasses MUST override this if the upstream API uses a different scheme.
        """
        return f"{self.base_url}?query={drug_name}"

    def build_headers(self) -> dict[str, str]:
        """Return request headers.

        Sends ``Accept: application/json`` by default (B2 fix).
        Subclasses may override to add or replace headers.
        """
        return {"Accept": "application/json"}

    async def invoke(self, drug_name: str) -> dict[str, Any]:
        """Invoke the tool and return a normalised response dict.

        Uses follow_redirects=True (B1 fix) and checks Content-Type before
        calling response.json() (B3 fix).
        """
        url = self.build_url(drug_name)
        headers = self.build_headers()

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return {
                    "tool": self.tool_name,
                    "error": (
                        f"Non-JSON response from upstream API "
                        f"(content-type: {content_type!r}). "
                        "This source may require credentials or uses a non-JSON format."
                    ),
                    "status_code": response.status_code,
                    "data": None,
                }

            return {
                "tool": self.tool_name,
                "data": response.json(),
                "status_code": response.status_code,
                "error": None,
            }
