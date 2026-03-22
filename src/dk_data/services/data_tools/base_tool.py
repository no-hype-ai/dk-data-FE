"""Base Data Tool — external fetch + raw insert + transform trigger.

The read path (gold/silver lookup) is now handled by PostgREST via the
route layer. This class only handles:
1. Rate-limited external API fetch (with retry + backoff)
2. Raw table insertion
3. Transform pipeline trigger (raw → bronze → silver → gold)

For molecule tools: delegates to the existing BaseMCPTool.
For CMS queryable: uses the CMS adapter directly.
"""

import asyncio
import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from .tool_registry import DataToolDefinition

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class BaseDataTool:
    """Handles external fetch + backfill for the data-tools gateway."""

    def __init__(
        self,
        tool_def: DataToolDefinition,
        db_pool=None,
    ):
        self.tool_def = tool_def
        self.db_pool = db_pool

    async def _invoke_external(
        self,
        request_id: str,
        params: Dict[str, Any],
        query_keys: Dict[str, str],
    ) -> Dict[str, Any]:
        """Invoke external API fetch, insert raw, trigger transform.

        For molecule tools: delegates to the existing BaseMCPTool.
        For CMS queryable tools: uses the CMS adapter directly with retry.

        Returns:
            Result dict with status, data, raw_record_id, transform_status, etc.
        """
        import importlib

        # Lazy-import adapter
        adapter_mod = importlib.import_module(self.tool_def.adapter_module)
        adapter_cls = getattr(adapter_mod, "Adapter", None)

        if adapter_cls is None:
            return self._error_response(
                request_id, "not_implemented",
                f"Adapter not implemented for {self.tool_def.name}", 501,
            )

        adapter = adapter_cls()

        if self.tool_def.category == "molecule":
            # Delegate to existing pipeline machinery for molecule tools
            from ..pipeline.base_tool import BaseMCPTool
            mcp_tool = BaseMCPTool(
                adapter=adapter,
                api_base_url=self.tool_def.api_base_url,
                db_pool=self.db_pool,
            )
            result = await mcp_tool.invoke(params)
            result["data_origin"] = "external_fetch"
            result["external_api_available"] = True
            return result

        # CMS queryable tools: adapter handles its own fetch
        from ..pipeline.rate_limiter import get_rate_limiter
        rate_limiter = get_rate_limiter()

        # Rate limit check — per-source bucket + global CMS bucket
        source_key = self.tool_def.raw_table
        if not await rate_limiter.acquire(source_key):
            from ...observability.metrics import record_cms_rate_limit_rejection
            record_cms_rate_limit_rejection(self.tool_def.name)
            return self._error_response(
                request_id, "rate_limited",
                f"Rate limit exceeded for {self.tool_def.name}", 429,
            )

        # Global CMS rate limit (max 8 req/s across all CMS datasets)
        if source_key.startswith("cms_"):
            if not await rate_limiter.acquire("_cms_global"):
                from ...observability.metrics import record_cms_rate_limit_rejection
                record_cms_rate_limit_rejection(self.tool_def.name)
                return self._error_response(
                    request_id, "rate_limited",
                    "Global CMS rate limit exceeded (8 req/s across all datasets)", 429,
                )

        # Fetch from external API via adapter (with retry + backoff)
        timeout = rate_limiter.get_timeout(source_key)
        backoff_cfg = rate_limiter.get_backoff_config(source_key)

        fetch_start = time.monotonic()
        try:
            api_response = await self._fetch_with_retry(
                adapter, query_keys, timeout, backoff_cfg,
            )
            fetch_duration = time.monotonic() - fetch_start
            from ...observability.metrics import record_cms_fetch, record_cms_external_api_request
            record_cms_external_api_request(self.tool_def.name, success=True)
        except Exception:
            fetch_duration = time.monotonic() - fetch_start
            from ...observability.metrics import record_cms_external_api_request
            record_cms_external_api_request(self.tool_def.name, success=False)
            raise

        normalized = adapter.normalize(api_response)
        record_count = len(normalized) if isinstance(normalized, list) else 1
        record_cms_fetch(self.tool_def.name, fetch_duration, record_count)

        # Insert into raw table
        raw_record_id = await self._insert_raw_record(
            request_id, params, api_response,
        )

        # Trigger transform pipeline — track success/failure
        transform_status = "skipped"
        transform_error = None
        if raw_record_id and self.db_pool:
            transform_status, transform_error = await self._trigger_transform(
                raw_record_id, api_response, params,
            )

        return {
            "status": "success",
            "request_id": request_id,
            "source": self.tool_def.name,
            "data_origin": "external_fetch",
            "data": normalized,
            "record_count": len(normalized) if isinstance(normalized, list) else 1,
            "raw_record_id": raw_record_id,
            "external_api_available": True,
            "transform_status": transform_status,
            "transform_error": transform_error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _fetch_with_retry(
        self,
        adapter,
        query_keys: Dict[str, str],
        timeout: float,
        backoff_cfg: dict,
    ) -> Any:
        """Fetch from external API with exponential backoff retry.

        Uses the backoff config from rate_limits.yaml (base_delay, max_delay,
        max_retries, jitter) that was previously unused.
        """
        max_retries = backoff_cfg.get("max_retries", 3)
        base_delay = backoff_cfg.get("base_delay", 1)
        max_delay = backoff_cfg.get("max_delay", 30)
        use_jitter = backoff_cfg.get("jitter", True)

        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return await adapter.fetch(
                    query_keys, timeout=timeout, base_url=self.tool_def.api_base_url,
                )
            except Exception as e:
                last_exception = e
                error_str = str(e)

                # Check if the error is retryable
                is_retryable = False
                for code in _RETRYABLE_STATUS_CODES:
                    if str(code) in error_str:
                        is_retryable = True
                        break

                # Also retry on timeout/connection errors
                if "timeout" in error_str.lower() or "connect" in error_str.lower():
                    is_retryable = True

                if not is_retryable or attempt >= max_retries:
                    raise

                # Exponential backoff: base_delay * 2^attempt
                delay = min(base_delay * (2 ** attempt), max_delay)
                if use_jitter:
                    delay = delay * (0.5 + random.random())

                logger.warning(
                    f"Fetch attempt {attempt + 1}/{max_retries + 1} failed for "
                    f"{self.tool_def.name}: {e}. Retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)

        raise last_exception  # type: ignore[misc]

    async def _insert_raw_record(
        self,
        request_id: str,
        params: Dict[str, Any],
        api_response: Any,
    ) -> Optional[str]:
        """Insert raw API response into the raw table."""
        if self.db_pool is None:
            return None

        try:
            record_id = str(uuid.uuid4())
            schema = self.tool_def.raw_schema
            table = self.tool_def.raw_table

            async with self.db_pool.acquire() as conn:
                await conn.execute(f"""
                    INSERT INTO {schema}.{table}
                    (id, request_id, request_timestamp, api_endpoint,
                     request_params, response_status, response_body,
                     processed_to_bronze, ingested_at)
                    VALUES ($1, $2, NOW(), $3, $4::jsonb, 200, $5::jsonb, FALSE, NOW())
                """,
                    record_id, request_id, self.tool_def.api_base_url,
                    json.dumps(params, default=str),
                    json.dumps(api_response, default=str),
                )
            return record_id
        except Exception as e:
            logger.error(f"Failed to insert raw record for {self.tool_def.name}: {e}")
            return None

    # Maps raw_table name → ordered SQLMesh model chain to run hot after ingest.
    # Bronze model is always first; downstream silver/gold follow.
    # All molecule tools now use SQLMesh — no Python transformer classes.
    _MOLECULE_MODEL_CHAINS: Dict[str, List[str]] = {
        'clinicaltrials':  ['mol_bronze.clinicaltrials',    'mol_silver.clinical_trials'],
        'openfda_labels':  ['mol_bronze.openfda_labels',    'mol_silver.drug_labels'],
        'openfda_faers':   ['mol_bronze.faers_events',      'mol_silver.adverse_events'],
        'chembl':          ['mol_bronze.chembl_molecules',   'mol_silver.molecules', 'mol_silver.bioactivity'],
        'pubchem':         ['mol_bronze.pubchem',            'mol_silver.molecules'],
        'uniprot':         ['mol_bronze.uniprot',            'mol_silver.targets'],
        'openalex':        ['mol_bronze.openalex',           'mol_silver.publications'],
        'europepmc':       ['mol_bronze.europepmc',          'mol_silver.publications'],
        'pubmed':          ['mol_bronze.pubmed',             'mol_silver.publications'],
        'bindingdb':       ['mol_bronze.bindingdb',          'mol_silver.bioactivity'],
        'ema':             ['mol_bronze.ema',                'mol_silver.regulatory_decisions'],
        'purple_book':     ['mol_bronze.purple_book',        'mol_silver.patent_exclusivities'],
        'orange_book':     ['mol_bronze.orange_book',        'mol_silver.patent_exclusivities'],
        'drugbank':        ['mol_bronze.drugbank',           'mol_silver.molecules'],
        'dailymed':        ['mol_bronze.dailymed',           'mol_silver.dailymed_labels'],
        'sider':           ['mol_bronze.sider',              'mol_silver.adverse_events'],
        'who_inn':         ['mol_bronze.who_inn',            'mol_silver.molecule_aliases'],
        'rxnorm':          ['mol_bronze.rxnorm_concepts',    'mol_silver.identifier_mappings'],
        'kegg_drug':       ['mol_bronze.kegg_drug',          'mol_silver.molecule_targets'],
        'tdc_admet':       ['mol_bronze.tdc_admet'],
        'pharmgkb':        ['mol_bronze.pharmgkb'],
        'websearch':       ['mol_bronze.websearch_results'],
        'uspto_patents':   ['mol_bronze.uspto_patents',      'mol_silver.patents'],
        'epo_patents':     ['mol_bronze.epo_patents',        'mol_silver.patents'],
        'sec_edgar':       ['mol_bronze.sec_edgar',          'mol_silver.financial_data'],
        'who_gho':         ['mol_bronze.who_gho',            'mol_silver.indication_epidemiology'],
        'ct_gov_indication_stats': ['mol_bronze.ct_gov_indication_stats'],
        'cochrane_reviews': ['mol_bronze.cochrane_reviews',  'mol_silver.publications'],
    }

    async def _trigger_transform(
        self,
        raw_record_id: str,
        api_response: Any,
        params: Dict[str, Any],
    ) -> tuple[str, Optional[str]]:
        """Trigger raw → bronze → silver → gold transform pipeline via hot SQLMesh run.

        All tools (both molecule and CMS) now use the same SQLMesh hot-run path.
        Returns (transform_status, transform_error).
        """
        return await self._trigger_sqlmesh_hot()

    async def _trigger_sqlmesh_hot(self) -> tuple[str, Optional[str]]:
        """Hot SQLMesh run for the current tool's model chain.

        Runs `sqlmesh run --select-model <model>` for each model in the chain
        (bronze → silver → gold) immediately after raw ingest, so data is
        available without waiting for the next scheduled cron run.

        Falls back to "pending" (data propagates on next scheduled run) when
        sqlmesh binary is not available in PATH.
        """
        import shutil
        import os

        sqlmesh_bin = shutil.which("sqlmesh")
        if not sqlmesh_bin:
            logger.info(
                f"sqlmesh not in PATH — {self.tool_def.name} data stored in raw, "
                "will propagate on next scheduled SQLMesh run"
            )
            return ("pending", "sqlmesh not available; data propagates on next scheduled run")

        # Resolve SQLMesh project path: baked into image at /app/sqlmesh,
        # or overridden via SQLMESH_PROJECT_PATH env var for local dev.
        sqlmesh_project = os.environ.get("SQLMESH_PROJECT_PATH", "/app/sqlmesh")

        # Resolve model chain: molecule tools use _MOLECULE_MODEL_CHAINS;
        # CMS / other tools fall back to local_check tables.
        source = self.tool_def.raw_table
        models: List[str] = list(self._MOLECULE_MODEL_CHAINS.get(source, []))

        if not models:
            # CMS or dynamically registered source — derive from tool definition
            models = [f"mol_bronze.{source}"]
            lc = getattr(self.tool_def, 'local_check', None)
            if lc and getattr(lc, 'silver_table', None):
                models.append(f"mol_silver.{lc.silver_table}")
            if lc and getattr(lc, 'gold_table', None):
                models.append(f"mol_gold.{lc.gold_table}")

        model_args: List[str] = []
        for m in models:
            model_args.extend(["--select-model", m])

        try:
            proc = await asyncio.create_subprocess_exec(
                sqlmesh_bin, "--paths", sqlmesh_project, "--gateway", "local",
                "run", *model_args, "--no-prompts",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",  # writable CWD for SQLMesh log dir
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                logger.info(f"SQLMesh hot run completed for {self.tool_def.name}: {models}")
                return ("completed", None)
            else:
                msg = stderr.decode()[:500]
                logger.warning(
                    f"SQLMesh hot run returned {proc.returncode} for {self.tool_def.name}: {msg}"
                )
                return ("failed", f"sqlmesh exit {proc.returncode}: {msg}")
        except asyncio.TimeoutError:
            logger.warning(f"SQLMesh hot run timed out for {self.tool_def.name}")
            return ("failed", "sqlmesh timed out after 120s")
        except Exception as e:
            logger.warning(
                f"SQLMesh hot run skipped for {self.tool_def.name}: {e}. "
                "Data in raw will propagate on next scheduled run."
            )
            return ("pending", str(e))

    def _error_response(
        self,
        request_id: str,
        error_code: str,
        message: str,
        status_code: int,
        duration_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "error",
            "request_id": request_id,
            "source": self.tool_def.name,
            "error": {
                "code": error_code,
                "message": message,
                "status_code": status_code,
            },
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
