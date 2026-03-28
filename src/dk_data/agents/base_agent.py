"""Base agent class for all DK Data LLM agents.

Feature: 019-cms-puf-platform-reconciliation
Task: T006

All agents extend BaseAgent. Key guarantees:
- LLM calls route via LiteLLM proxy (openai SDK) — NEVER direct provider calls
- 'import anthropic' is FORBIDDEN in this module and all subclasses
- Quality escalation: pharma-llm first → claude-sonnet-4-20250514 if confidence < 0.6
- Max 5 concurrent LLM calls per agent run (semaphore-guarded)
- DB writes to silver tables use asyncpg (agents are async; cannot use psycopg2 get_cursor())
- Batch size cap: limit defaults to MAX_EVIDENCE_PER_PILLAR (50) per ARCHITECTURE-BEST-PRACTICES.md
- Failed records go to agents.agent_quarantine — never abort the batch
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import asyncpg
import structlog
from openai import AsyncOpenAI, RateLimitError, APIStatusError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from dk_data.observability.metrics import record_agent_run as _record_agent_run
except ImportError:
    _record_agent_run = None  # type: ignore

# Canonical limit from ARCHITECTURE-BEST-PRACTICES.md
MAX_EVIDENCE_PER_PILLAR: int = 50

# Concurrent LLM call cap (shared 500 RPM across all DataKinetic services)
MAX_CONCURRENT_LLM_CALLS: int = 5

# Quality escalation threshold
ESCALATION_CONFIDENCE_THRESHOLD: float = 0.6

logger = structlog.get_logger(__name__)


@dataclass
class AgentResult:
    """Result from processing a single record."""
    record_id: str
    success: bool
    output: Optional[dict] = None
    confidence_score: Optional[float] = None
    needs_review: bool = False
    error: Optional[str] = None


@dataclass
class RunResult:
    """Summary result from a complete agent run."""
    agent_name: str
    records_processed: int = 0
    records_written: int = 0
    records_quarantined: int = 0
    records_needs_review: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "success"


class BaseAgent(ABC):
    """Abstract base class for all DK Data LLM agents.

    Subclasses must implement:
        - fetch_records(scope, limit) -> list[dict]
        - extract_fields(record, llm_response) -> dict
        - write_results(results, db_pool) -> int  (async, writes to silver table)
        - AGENT_NAME: str class attribute
        - SILVER_TABLE: str class attribute  (schema.table_name)
    """

    AGENT_NAME: str = "base_agent"
    SILVER_TABLE: str = ""

    def __init__(self, model: str = "pharma-llm") -> None:
        """
        Initialize the agent.

        Args:
            model: LiteLLM model alias for the primary call (default: pharma-llm).
                   Quality escalation will use 'claude-sonnet-4-20250514' if confidence < 0.6.
        """
        self._model = model
        self._escalation_model = "claude-sonnet-4-20250514"

        litellm_url = os.environ["LITELLM_PROXY_URL"]
        litellm_key = os.environ["LITELLM_API_KEY"]

        # OpenAI SDK pointed at LiteLLM proxy — NOT anthropic SDK
        self._client = AsyncOpenAI(
            base_url=litellm_url,
            api_key=litellm_key,
        )

        # Semaphore: max concurrent LLM calls
        self._llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

        # asyncpg pool — agents are async; cannot reuse psycopg2 get_cursor()
        self._db_pool: Optional[asyncpg.Pool] = None

        # Cost tracking: accumulated token usage for the current run
        self._run_input_tokens: int = 0
        self._run_output_tokens: int = 0
        self._run_escalated_calls: int = 0

        logger.info(
            "agent_initialized",
            agent=self.AGENT_NAME,
            model=self._model,
            litellm_url=litellm_url,
        )

    async def _get_db_pool(self) -> asyncpg.Pool:
        """Lazy-initialize asyncpg connection pool."""
        if self._db_pool is None:
            dsn = os.environ["DATABASE_URL"]
            self._db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
        return self._db_pool

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((RateLimitError, APIStatusError)),
        reraise=True,
    )
    async def _call_llm_raw(self, prompt: str, model: str) -> str:
        """Call LiteLLM via openai SDK with tenacity retry for 429/5xx."""
        async with self._llm_semaphore:
            response = await self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        if response.usage:
            self._run_input_tokens += response.usage.prompt_tokens or 0
            self._run_output_tokens += response.usage.completion_tokens or 0
        return response.choices[0].message.content or ""

    async def _call_llm(self, prompt: str, record_id: str) -> str:
        """Call LiteLLM with retry. Returns raw text response."""
        try:
            return await self._call_llm_raw(prompt, self._model)
        except Exception as e:
            logger.warning("llm_call_failed", agent=self.AGENT_NAME, record_id=record_id, error=str(e))
            raise

    async def _call_llm_with_escalation(
        self, prompt: str, record_id: str
    ) -> tuple[str, float]:
        """
        Call pharma-llm first; escalate to frontier model if confidence < threshold.

        Returns:
            (llm_response_text, confidence_score)
        """
        # First attempt: pharma-llm
        first_response = await self._call_llm_raw(prompt, self._model)
        first_confidence = self._parse_confidence(first_response)

        if first_confidence >= ESCALATION_CONFIDENCE_THRESHOLD:
            logger.debug(
                "no_escalation_needed",
                agent=self.AGENT_NAME,
                record_id=record_id,
                confidence=first_confidence,
            )
            return first_response, first_confidence

        # One escalation maximum: call frontier model
        logger.info(
            "escalating_to_frontier",
            agent=self.AGENT_NAME,
            record_id=record_id,
            first_confidence=first_confidence,
            escalation_model=self._escalation_model,
        )
        escalated_response = await self._call_llm_raw(prompt, self._escalation_model)
        escalated_confidence = self._parse_confidence(escalated_response)
        self._run_escalated_calls += 1
        return escalated_response, escalated_confidence

    def _parse_confidence(self, llm_response: str) -> float:
        """
        Parse confidence score from LLM response.
        Subclasses should override with structured output parsing.
        Default: return 0.0 to force escalation (safe fallback).
        """
        return 0.0

    async def _process_batch(self, records: list[dict]) -> list[AgentResult]:
        """
        Process a batch of records concurrently.

        Uses asyncio.gather with return_exceptions=True — one failed record
        does NOT abort the batch. Failures produce AgentResult(success=False).
        """
        tasks = [self._process_single(record) for record in records]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[AgentResult] = []
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                record_id = str(records[i].get("id", i))
                logger.warning(
                    "record_processing_failed",
                    agent=self.AGENT_NAME,
                    record_id=record_id,
                    error=str(r),
                )
                results.append(AgentResult(
                    record_id=record_id,
                    success=False,
                    error=str(r),
                ))
            else:
                results.append(r)  # type: ignore[arg-type]
        return results

    @abstractmethod
    async def _process_single(self, record: dict) -> AgentResult:
        """Process a single record. Subclasses implement this."""
        ...

    @abstractmethod
    async def fetch_records(self, scope: Any, limit: int) -> list[dict]:
        """Fetch records to process from the source table."""
        ...

    @abstractmethod
    async def write_results(
        self, results: list[AgentResult], db_pool: asyncpg.Pool
    ) -> int:
        """Write successful results to the silver table. Returns rows written."""
        ...

    async def _write_quarantine(self, record: dict, result: AgentResult) -> None:
        """Write a failed/low-confidence record to agents.agent_quarantine."""
        db_pool = await self._get_db_pool()
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agents.agent_quarantine
                    (agent_name, record_id, source_table, raw_input, agent_output,
                     confidence_score, failure_reason)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                self.AGENT_NAME,
                result.record_id,
                self.SILVER_TABLE,
                str(record),
                str(result.output) if result.output else None,
                result.confidence_score,
                result.error or "confidence_below_threshold",
            )

    async def _flag_needs_review(self, record: dict, result: AgentResult) -> None:
        """Mark a record as needs_review (confidence 0.5–0.79). Subclasses override."""
        # Base implementation: just log. Subclasses set needs_review=True in write_results.
        logger.info(
            "record_needs_review",
            agent=self.AGENT_NAME,
            record_id=result.record_id,
            confidence=result.confidence_score,
        )

    async def run(self, scope: Any = None, limit: int = MAX_EVIDENCE_PER_PILLAR) -> RunResult:
        """
        Execute the agent for a given scope.

        Args:
            scope: Source filter (e.g., date range, molecule_id). Agent-specific.
            limit: Max records to process per run (default: MAX_EVIDENCE_PER_PILLAR = 50).

        Returns:
            RunResult with counts and status.
        """
        run_result = RunResult(agent_name=self.AGENT_NAME)

        logger.info("agent_run_started", agent=self.AGENT_NAME, limit=limit)

        try:
            records = await self.fetch_records(scope, limit)
            run_result.records_processed = len(records)

            if not records:
                logger.info("no_records_to_process", agent=self.AGENT_NAME)
                return run_result

            results = await self._process_batch(records)
            db_pool = await self._get_db_pool()

            # Partition results by outcome
            successful = []
            for record, result in zip(records, results):
                if not result.success:
                    await self._write_quarantine(record, result)
                    run_result.records_quarantined += 1
                    run_result.errors.append(f"{result.record_id}: {result.error}")
                elif result.confidence_score is not None and result.confidence_score < 0.5:
                    result.success = False
                    await self._write_quarantine(record, result)
                    run_result.records_quarantined += 1
                elif result.confidence_score is not None and result.confidence_score < 0.8:
                    result.needs_review = True
                    successful.append(result)
                    run_result.records_needs_review += 1
                else:
                    successful.append(result)

            if successful:
                written = await self.write_results(successful, db_pool)
                run_result.records_written = written

        except Exception as e:
            run_result.status = "error"
            run_result.errors.append(str(e))
            logger.error("agent_run_failed", agent=self.AGENT_NAME, error=str(e))
        finally:
            if self._db_pool:
                await self._db_pool.close()

        # Estimate LLM cost: pharma-llm ~$0.0002/1K tokens, frontier ~$0.015/1K tokens
        primary_tokens = max(0, self._run_input_tokens + self._run_output_tokens
                             - self._run_escalated_calls * 2000)  # rough split
        escalated_tokens = self._run_escalated_calls * 2000
        estimated_cost = (primary_tokens / 1000 * 0.0002) + (escalated_tokens / 1000 * 0.015)

        logger.info(
            "agent_run_completed",
            agent=self.AGENT_NAME,
            records_processed=run_result.records_processed,
            records_written=run_result.records_written,
            records_quarantined=run_result.records_quarantined,
            input_tokens=self._run_input_tokens,
            output_tokens=self._run_output_tokens,
            escalated_calls=self._run_escalated_calls,
            estimated_cost_usd=round(estimated_cost, 4),
            status=run_result.status,
        )

        if _record_agent_run is not None:
            try:
                _record_agent_run(
                    agent_name=self.AGENT_NAME,
                    records_written=run_result.records_written,
                    records_quarantined=run_result.records_quarantined,
                    cost_usd=estimated_cost,
                    status=run_result.status,
                )
            except Exception:
                pass  # Never let metrics recording break a run

        return run_result
