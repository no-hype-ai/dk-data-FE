"""Base MCP data-tool adapter — stateless fetch + medallion raw write.

Fixes applied (issue #188):
  B1 - follow_redirects=True (was False, broke TTD and others)
  B2 - Accept: application/json default header (was absent, ORCID returned XML)
  B3 - Content-Type check before response.json() (was unconditional, caused JSONDecodeError)

Medallion write path (issue #191 — preserved from original design):
  After a successful API response, the raw JSON is written to the appropriate
  mol_raw.* table (if raw_schema and raw_table are set on the subclass).
  This ensures MCP on-demand queries feed the standard bronze→silver→gold
  pipeline on the next SQLMesh run — adapters are not a bypass of the
  medallion architecture.

  Adapters that are bulk-only (ema, cochrane, ttd) override invoke() entirely
  and never reach the raw write path.
"""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BaseMCPTool(ABC):
    """Abstract base for all MCP data-tool adapters."""

    tool_name: str = ""
    base_url: str = ""

    # Override in subclasses to enable medallion raw write.
    # Leave empty to skip the raw insert (e.g. bulk-only adapters).
    raw_schema: str = ""
    raw_table: str = ""

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
        """Invoke the tool, write raw response to mol_raw.*, and return result.

        Flow:
          1. Build URL + headers (adapter-specific overrides apply)
          2. Fetch from upstream API with follow_redirects=True (B1 fix)
          3. Check Content-Type before parsing JSON (B3 fix)
          4. Write raw response to mol_raw.{raw_table} (medallion raw layer)
          5. Return structured result dict
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

            data = response.json()

            # Medallion raw write — fire and forget; never blocks the response.
            if self.raw_schema and self.raw_table:
                self._write_to_raw(drug_name, url, response.status_code, data)

            return {
                "tool": self.tool_name,
                "data": data,
                "status_code": response.status_code,
                "error": None,
            }

    def _write_to_raw(
        self,
        drug_name: str,
        url: str,
        status_code: int,
        response_data: Any,
    ) -> None:
        """Insert raw API response into mol_raw.{raw_table} (synchronous psycopg2).

        Failures are logged and silently swallowed — the raw write must never
        break the MCP invoke response returned to the caller.
        """
        try:
            from dk_data.ingestion.utils.database import get_cursor  # lazy import

            request_id = str(uuid.uuid4())
            with get_cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {self.raw_schema}.{self.raw_table}
                        (request_id, request_timestamp, api_endpoint,
                         request_params, response_status, response_body,
                         processed_to_bronze, ingested_at, source_id)
                    VALUES
                        (%s, NOW(), %s, %s::jsonb, %s, %s::jsonb, FALSE, NOW(), %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        request_id,
                        url,
                        json.dumps({"drug_name": drug_name}),
                        status_code,
                        json.dumps(response_data),
                        self.tool_name,
                    ),
                )
            logger.debug(
                "MCP raw write: %s.%s ← %s (request_id=%s)",
                self.raw_schema, self.raw_table, self.tool_name, request_id,
            )
        except Exception as exc:
            # Never surface DB errors to the MCP caller.
            logger.warning(
                "MCP raw write failed for %s.%s: %s",
                self.raw_schema, self.raw_table, exc,
            )
