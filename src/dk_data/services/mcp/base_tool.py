"""Base MCP data-tool — concrete class that wraps an adapter with drug resolution.

Feature: 019-cms-puf-platform-reconciliation

Fixes from original ABC implementation:
  - B1: follow_redirects=True (was False, broke TTD and others)
  - B2: Accept + User-Agent headers on every request
  - B3: Content-Type check before response.json()
  - B4: Resolution-aware multi-URL fallback (new)
  - B5: Empty-result detection so we skip stale/empty API pages
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class BaseMCPTool:
    """Concrete MCP tool that wraps a BaseAdapter and drives the HTTP fetch loop.

    Instantiated by _build_tool() in data_tools.py:
        BaseMCPTool(adapter=adapter, api_base_url=..., db_pool=...)

    Resolution-aware: if input_params contains ``_resolution`` (a DrugResolution
    object produced by DrugResolver), the adapter's build_urls_with_resolution()
    method is called to get an ordered list of URLs to try.  Falls back to a
    single URL from build_url() when no resolution is available.
    """

    _DEFAULT_HEADERS: Dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "dk-data-platform research@dk-data.com",
    }

    def __init__(
        self,
        adapter=None,
        api_base_url: Optional[str] = None,
        db_pool=None,
    ) -> None:
        self.adapter = adapter
        self.api_base_url = api_base_url
        self.db_pool = db_pool

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def invoke(self, input_params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch data for the given input parameters.

        Args:
            input_params: Must contain ``drug_name``.  May contain
                ``_resolution`` (a DrugResolution) and ``molecule_id``.

        Returns:
            Dict with ``status``, ``source``, ``drug_name``,
            ``resolution_source``, ``data``, and (on error) ``error``.
        """
        # Support old-style invocation: invoke(drug_name: str) from router.py
        if isinstance(input_params, str):
            input_params = {"drug_name": input_params}

        drug_name: str = input_params.get("drug_name", "")
        resolution = input_params.get("_resolution")  # DrugResolution | None

        # Build ordered URL list — multi-URL when resolution is available
        urls: List[str] = self._build_urls(drug_name, resolution, input_params)

        last_error: Optional[str] = None

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers=self._DEFAULT_HEADERS,
        ) as client:
            for url in urls:
                try:
                    resp = await client.get(url)

                    if resp.status_code == 404:
                        last_error = f"404 Not Found: {url}"
                        continue  # try next URL

                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "")
                    if "json" not in content_type:
                        last_error = (
                            f"Non-JSON response (content-type: {content_type!r}) from {url}"
                        )
                        continue

                    data = resp.json()
                    normalized = (
                        self.adapter.normalize(data)
                        if self.adapter is not None
                        else data
                    )

                    if self._is_empty_result(data):
                        last_error = f"Empty result from {url}"
                        continue  # try next URL / alias

                    resolution_source = (
                        resolution.resolution_source if resolution else "none"
                    )
                    _source = (
                        self.adapter.source_name
                        if self.adapter is not None
                        else getattr(self, "tool_name", "unknown")
                    )
                    logger.info(
                        "base_tool.invoke_success",
                        source=_source,
                        drug_name=drug_name,
                        resolution_source=resolution_source,
                        url=url,
                    )
                    return {
                        "status": "ok",
                        "source": _source,
                        "url": url,
                        "drug_name": drug_name,
                        "resolution_source": resolution_source,
                        "data": normalized,
                    }

                except httpx.HTTPStatusError as exc:
                    last_error = str(exc)
                    if exc.response.status_code in (401, 403, 429, 500, 502, 503):
                        # Do not retry on auth / server errors
                        break
                    continue
                except Exception as exc:
                    last_error = str(exc)
                    continue

        # All URLs exhausted
        resolution_source = resolution.resolution_source if resolution else "none"
        _source = (
            self.adapter.source_name
            if self.adapter is not None
            else getattr(self, "tool_name", "unknown")
        )
        logger.warning(
            "base_tool.invoke_failed",
            source=_source,
            drug_name=drug_name,
            resolution_source=resolution_source,
            error=last_error,
        )
        return {
            "status": "error",
            "source": _source,
            "drug_name": drug_name,
            "resolution_source": resolution_source,
            "error": {
                "message": last_error or "No results found",
                "status_code": 502,
            },
            "data": None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_urls(
        self,
        drug_name: str,
        resolution,
        input_params: Dict[str, Any],
    ) -> List[str]:
        """Return ordered list of URLs to try for this invocation."""
        # Old-style subclass: no adapter; tool defines build_url(drug_name) directly
        if self.adapter is None:
            return [self.build_url(drug_name)]  # type: ignore[attr-defined]

        if resolution is not None and hasattr(
            self.adapter, "build_urls_with_resolution"
        ):
            try:
                return self.adapter.build_urls_with_resolution(
                    self.api_base_url, resolution, input_params
                )
            except Exception as exc:
                logger.warning(
                    "base_tool.build_urls_with_resolution_failed",
                    source=self.adapter.source_name,
                    error=str(exc),
                )

        # Fallback: single URL using raw drug_name
        return [self.adapter.build_url(self.api_base_url, drug_name, input_params)]

    def _is_empty_result(self, data: Any) -> bool:
        """Return True when the API response contains no useful records."""
        if not data:
            return True
        if not isinstance(data, dict):
            return False

        # OpenFDA pattern: {"results": [...]}
        if "results" in data and not data["results"]:
            return True

        # EDGAR / Elasticsearch pattern: {"hits": {"hits": [...]}}
        if "hits" in data:
            hits = data["hits"]
            if isinstance(hits, dict):
                return len(hits.get("hits", [])) == 0
            return len(hits) == 0

        # Generic error body
        if data.get("error"):
            return True

        return False
