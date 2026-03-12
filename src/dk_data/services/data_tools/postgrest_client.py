"""PostgREST client — unified read path for all data-tools queries.

All local data reads go through PostgREST, which enforces the same JWT
role-based access control that external consumers use. This eliminates
the dual-path problem (direct SQL vs PostgREST) and ensures one auth model.

PostgREST serves from the ``api`` schema (thin wrappers over gold views)
and can also query ``gold``, ``silver``, ``bronze`` schemas directly.
"""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from loguru import logger


def _postgrest_base_url() -> str:
    """Resolve PostgREST base URL from environment."""
    return os.getenv("POSTGREST_URL", "http://postgrest:3000")


class PostgRESTClient:
    """Async client for querying PostgREST with JWT auth forwarding.

    Args:
        jwt_token: Bearer token to forward. If None, queries as anonymous
                   (web_anon role — read-only on api schema).
        base_url:  PostgREST base URL. Defaults to POSTGREST_URL env var
                   or ``http://postgrest:3000``.
    """

    def __init__(
        self,
        jwt_token: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.base_url = (base_url or _postgrest_base_url()).rstrip("/")
        self._headers: Dict[str, str] = {
            "Accept": "application/json",
            "Prefer": "count=exact",
        }
        if jwt_token:
            self._headers["Authorization"] = f"Bearer {jwt_token}"

    async def query_view(
        self,
        schema: str,
        table: str,
        key_column: str,
        value: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query a PostgREST-exposed view by key column.

        Uses the Accept-Profile header to select the schema
        (api, gold, silver, bronze, etc.).

        Returns:
            List of row dicts, or empty list.
        """
        headers = {
            **self._headers,
            "Accept-Profile": schema,
        }
        # PostgREST filter: ?key_column=eq.value
        url = (
            f"{self.base_url}/{quote(table)}"
            f"?{quote(key_column)}=eq.{quote(value)}"
            f"&limit={limit}"
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    # View doesn't exist in this schema
                    return []
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, list) else [data]
        except httpx.HTTPStatusError as e:
            logger.debug(f"PostgREST query failed ({schema}.{table}): {e.response.status_code}")
            return []
        except Exception as e:
            logger.debug(f"PostgREST query error ({schema}.{table}): {e}")
            return []

    async def get_freshness(
        self,
        schema: str,
        table: str,
    ) -> Optional[Dict[str, Any]]:
        """Get row count and rough freshness from a PostgREST view.

        Uses HEAD + Content-Range to get count without transferring rows,
        then fetches one row ordered by a timestamp column (descending)
        to approximate last_updated.

        Returns:
            Dict with row_count, last_updated, freshness_hours, or None.
        """
        headers = {
            **self._headers,
            "Accept-Profile": schema,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # HEAD to get count from Content-Range
                head_resp = await client.head(
                    f"{self.base_url}/{quote(table)}?limit=0",
                    headers=headers,
                )
                if head_resp.status_code == 404:
                    return None
                head_resp.raise_for_status()

                # Parse Content-Range: */N or 0-0/N
                content_range = head_resp.headers.get("Content-Range", "")
                row_count = 0
                if "/" in content_range:
                    count_str = content_range.rsplit("/", 1)[-1]
                    if count_str.isdigit():
                        row_count = int(count_str)

                if row_count == 0:
                    return {
                        "schema": schema,
                        "table": table,
                        "row_count": 0,
                        "last_updated": None,
                        "freshness_hours": None,
                    }

                # Get newest row to approximate freshness.
                # Try common timestamp columns in priority order.
                for ts_col in ("last_refreshed", "gold_built_at", "profile_built_at",
                               "_loaded_at", "ingested_at", "updated_at", "created_at"):
                    ts_url = (
                        f"{self.base_url}/{quote(table)}"
                        f"?select={quote(ts_col)}"
                        f"&order={quote(ts_col)}.desc"
                        f"&limit=1"
                    )
                    ts_resp = await client.get(ts_url, headers=headers)
                    if ts_resp.status_code == 200:
                        rows = ts_resp.json()
                        if rows and rows[0].get(ts_col):
                            from datetime import datetime, timezone
                            last_ts = rows[0][ts_col]
                            try:
                                dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                                delta = datetime.now(timezone.utc) - dt
                                return {
                                    "schema": schema,
                                    "table": table,
                                    "row_count": row_count,
                                    "last_updated": last_ts,
                                    "freshness_hours": round(delta.total_seconds() / 3600, 2),
                                }
                            except (ValueError, TypeError):
                                pass

                # No timestamp column found — return count only
                return {
                    "schema": schema,
                    "table": table,
                    "row_count": row_count,
                    "last_updated": None,
                    "freshness_hours": None,
                }

        except Exception as e:
            logger.debug(f"PostgREST freshness check failed ({schema}.{table}): {e}")
            return None
