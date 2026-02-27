"""Base MCP tool class implementing the standard invoke flow.

Feature: 015-assessment-dashboard-integration
Task: T061

Flow: rate_limit → fetch_external_api → adapter.normalize() →
      insert_raw_record() → trigger_transform() → return_results
"""

import os
import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import httpx
from loguru import logger

from .adapters.base import BaseAdapter
from .rate_limiter import get_rate_limiter

# Maps source names to (env_var, param_type, param_name) for API key injection.
# param_type: "query" adds as URL param, "header" adds as Bearer token,
#             "oauth2_client_credentials" fetches a token first.
_SOURCE_AUTH_MAP: Dict[str, tuple] = {
    "openalex": ("OPENALEX_API_KEY", "query", "api_key"),
    "openfda_faers": ("OPENFDA_API_KEY", "query", "api_key"),
    "openfda_labels": ("OPENFDA_API_KEY", "query", "api_key"),
    "orange_book": ("OPENFDA_API_KEY", "query", "api_key"),
    "pubmed": ("NCBI_API_KEY", "query", "api_key"),
}

# WHO ICD-11 OAuth2 token cache
_WHO_ICD_TOKEN: Optional[str] = None
_WHO_ICD_TOKEN_EXPIRY: float = 0


class BaseMCPTool:
    """Base class for all MCP data retrieval tools.

    Each tool wraps an adapter and handles the full invoke lifecycle:
    1. Rate limit check
    2. Fetch from external API
    3. Normalize via adapter
    4. Insert into raw table
    5. Optionally trigger on-demand transform
    6. Return structured result
    """

    def __init__(
        self,
        adapter: BaseAdapter,
        api_base_url: str,
        db_pool=None,
    ):
        self.adapter = adapter
        self.api_base_url = api_base_url
        self.db_pool = db_pool
        self._rate_limiter = get_rate_limiter()

    @property
    def source_name(self) -> str:
        return self.adapter.source_name

    async def invoke(self, input_params: dict) -> dict:
        """Execute the MCP tool invocation flow.

        Args:
            input_params: Tool-specific input parameters (e.g., drug_name, molecule_id).

        Returns:
            ToolInvocationResponse dict with status, data, and metadata.
        """
        start_time = time.monotonic()
        request_id = str(uuid.uuid4())

        try:
            # 1. Rate limit check
            if not await self._rate_limiter.acquire(self.source_name):
                return self._error_response(
                    request_id, "rate_limited",
                    f"Rate limit exceeded for {self.source_name}", 429
                )

            # 2. Fetch data (local index for drugbank, external API for others)
            if self.source_name == "drugbank":
                api_response = self._lookup_drugbank(input_params)
            else:
                timeout = self._rate_limiter.get_timeout(self.source_name)
                api_response = await self._fetch_external(input_params, timeout)

            # 3. Normalize via adapter
            normalized = self.adapter.normalize(api_response)

            # 4. Insert into raw table
            raw_record_id = await self._insert_raw_record(
                request_id, input_params, api_response, normalized
            )

            # 5. Build response
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return {
                "status": "success",
                "request_id": request_id,
                "source": self.source_name,
                "data": normalized,
                "raw_record_id": raw_record_id,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except httpx.TimeoutException:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(f"Timeout fetching {self.source_name}: {duration_ms}ms")
            return self._error_response(
                request_id, "timeout",
                f"Request to {self.source_name} timed out", 408
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from {self.source_name}: {e.response.status_code}")
            return self._error_response(
                request_id, "external_api_error",
                f"External API {self.source_name} returned {e.response.status_code}", 502
            )
        except Exception as e:
            logger.error(f"MCP tool error for {self.source_name}: {e}")
            return self._error_response(
                request_id, "internal_error", str(e), 500
            )

    async def _fetch_external(self, params: dict, timeout: float) -> dict:
        """Fetch data from the external API. Override for custom request logic.

        Automatically injects API keys from environment variables for known
        sources (see _SOURCE_AUTH_MAP).  WHO ICD uses OAuth2 client credentials.
        """
        drug_name = params.get("drug_name", "")
        url = self._build_url(drug_name, params)

        # Inject API key if configured for this source
        query_params: Dict[str, str] = {}
        headers: Dict[str, str] = {}
        auth_config = _SOURCE_AUTH_MAP.get(self.source_name)
        if auth_config:
            env_var, auth_type, param_name = auth_config
            api_key = os.environ.get(env_var)
            if api_key:
                if auth_type == "query":
                    query_params[param_name] = api_key
                elif auth_type == "header":
                    headers["Authorization"] = f"Bearer {api_key}"

        # WHO ICD-11 requires OAuth2 client credentials
        if self.source_name == "who_icd":
            token = await self._get_who_icd_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                headers["Accept"] = "application/json"
                headers["Accept-Language"] = "en"
                headers["API-Version"] = "v2"

        # Append query_params to the URL manually to avoid httpx replacing
        # the existing query string built by the adapter's build_url().
        # httpx.Request(params=...) overwrites the URL's query string,
        # which strips adapter-built filters like ?search=openfda.generic_name:"X".
        if query_params:
            separator = "&" if "?" in url else "?"
            extra = "&".join(f"{k}={v}" for k, v in query_params.items())
            url = f"{url}{separator}{extra}"

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers or None)
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def _get_who_icd_token() -> Optional[str]:
        """Fetch WHO ICD-11 OAuth2 token using client credentials grant."""
        global _WHO_ICD_TOKEN, _WHO_ICD_TOKEN_EXPIRY

        # Return cached token if still valid
        if _WHO_ICD_TOKEN and time.monotonic() < _WHO_ICD_TOKEN_EXPIRY:
            return _WHO_ICD_TOKEN

        client_id = os.environ.get("WHO_ICD_CLIENT_ID")
        client_secret = os.environ.get("WHO_ICD_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.warning("WHO_ICD_CLIENT_ID / WHO_ICD_CLIENT_SECRET not set")
            return None

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://icdaccessmanagement.who.int/connect/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "icdapi_access",
                        "grant_type": "client_credentials",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                _WHO_ICD_TOKEN = data["access_token"]
                # Expire 60s early to avoid edge-case failures
                _WHO_ICD_TOKEN_EXPIRY = time.monotonic() + data.get("expires_in", 3600) - 60
                return _WHO_ICD_TOKEN
        except Exception as e:
            logger.error(f"Failed to obtain WHO ICD token: {e}")
            return None

    def _build_url(self, drug_name: str, params: dict) -> str:
        """Build the API URL. Delegates to adapter.build_url for source-specific logic."""
        return self.adapter.build_url(self.api_base_url, drug_name, params)

    async def _insert_raw_record(
        self,
        request_id: str,
        input_params: dict,
        api_response: dict,
        normalized: dict,
    ) -> Optional[str]:
        """Insert raw API response into the raw table."""
        if self.db_pool is None:
            logger.debug("No db_pool, skipping raw insert")
            return None

        try:
            record_id = str(uuid.uuid4())
            schema = self.adapter.raw_schema
            table = self.adapter.raw_table

            async with self.db_pool.acquire() as conn:
                await conn.execute(f"""
                    INSERT INTO {schema}.{table}
                    (id, request_id, request_timestamp, api_endpoint,
                     request_params, response_status, response_body,
                     processed_to_bronze, ingested_at)
                    VALUES ($1, $2, NOW(), $3, $4::jsonb, 200, $5::jsonb, FALSE, NOW())
                """,
                    record_id, request_id, self.api_base_url,
                    str(input_params), str(api_response),
                )
            return record_id
        except Exception as e:
            logger.error(f"Failed to insert raw record: {e}")
            return None

    @staticmethod
    def _lookup_drugbank(params: dict) -> dict:
        """Look up a drug in the local DrugBank XML index."""
        from .adapters.drugbank import get_drug_index

        drug_name = params.get("drug_name", "")
        index = get_drug_index()
        if index is None:
            raise RuntimeError("DrugBank XML not available. Set DRUGBANK_XML_PATH env var.")

        # Exact match first, then prefix search
        key = drug_name.lower().strip()
        entry = index.get(key)
        if not entry:
            # Try partial match
            matches = [v for k, v in index.items() if key in k]
            if matches:
                entry = matches[0]

        if not entry:
            return {"drugs": [], "query": drug_name, "source": "drugbank_local_xml"}

        return {"drugs": [entry], "query": drug_name, "source": "drugbank_local_xml"}

    def _error_response(self, request_id: str, error_code: str, message: str, status_code: int) -> dict:
        """Build a standard error response."""
        return {
            "status": "error",
            "request_id": request_id,
            "source": self.source_name,
            "error": {
                "code": error_code,
                "message": message,
                "status_code": status_code,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
