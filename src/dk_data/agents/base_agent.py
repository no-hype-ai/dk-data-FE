"""Base agent class for Silver+ enrichment.

All LLM calls route through LiteLLM proxy using OpenAI-compatible Python client.
Direct Anthropic SDK usage is forbidden per dk-canon.

Execution: K8s Jobs (not BullMQ — dk-data-FE is Python-only).
Logging: Append-only meta.agent_execution_log.
"""

import os
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

import psycopg2
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of an agent execution."""
    enriched: list[dict[str, Any]] = field(default_factory=list)
    quarantine: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class BaseAgent(ABC):
    """Abstract base for all Silver+ enrichment agents.

    Subclasses must implement:
        - AGENT_NAME: str
        - AGENT_VERSION: str
        - load_batch() -> list[dict]
        - execute(batch) -> AgentResult
        - write_results(enriched) -> None
    """

    AGENT_NAME: str = "base"
    AGENT_VERSION: str = "0.1.0"
    CONFIDENCE_THRESHOLD_ACCEPT: float = 0.8
    CONFIDENCE_THRESHOLD_REVIEW: float = 0.5

    # Cost per token for Haiku via LiteLLM (USD).
    # Updated periodically — these are Anthropic's public Haiku prices.
    _COST_PER_INPUT_TOKEN: float = 0.25 / 1_000_000   # $0.25/MTok
    _COST_PER_OUTPUT_TOKEN: float = 1.25 / 1_000_000   # $1.25/MTok

    def __init__(self):
        # LiteLLM via OpenAI-compatible client
        self.client = OpenAI(
            base_url=os.environ.get("LITELLM_BASE_URL", "http://litellm.infra.svc.cluster.local:8000"),
            api_key=os.environ.get("LITELLM_API_KEY", ""),
        )
        self.model = os.environ.get("LITELLM_MODEL_ALIAS", "haiku")

        # Database connection
        self._conn = None

        # Token usage tracking — accumulated across all call_llm invocations
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST", "localhost"),
                port=os.environ.get("POSTGRES_PORT", "5433"),
                user=os.environ.get("POSTGRES_USER", "dk_data"),
                password=os.environ.get("POSTGRES_PASSWORD", ""),
                dbname=os.environ.get("POSTGRES_DB", "dk_data"),
            )
        return self._conn

    def call_llm(self, messages: list[dict], temperature: float = 0.1) -> dict:
        """Call LLM via LiteLLM proxy. Returns parsed JSON response.

        Accumulates token usage for cost tracking in log_execution().
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
        )

        # Track token usage from response
        if response.usage:
            self._total_input_tokens += response.usage.prompt_tokens or 0
            self._total_output_tokens += response.usage.completion_tokens or 0

        import json
        content = response.choices[0].message.content
        return json.loads(content)

    @property
    def estimated_cost_usd(self) -> float:
        """Compute estimated cost from accumulated token usage."""
        return (
            self._total_input_tokens * self._COST_PER_INPUT_TOKEN
            + self._total_output_tokens * self._COST_PER_OUTPUT_TOKEN
        )

    @abstractmethod
    def load_batch(self) -> list[dict[str, Any]]:
        """Load input batch from bronze/silver tables."""
        ...

    @abstractmethod
    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Process batch and return enriched + quarantine records."""
        ...

    @abstractmethod
    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Write enriched records to silver target table."""
        ...

    def write_quarantine(self, quarantine: list[dict[str, Any]], execution_id: str) -> None:
        """Write quarantine records to meta.agent_quarantine."""
        if not quarantine:
            return

        import json
        with self.conn.cursor() as cur:
            for record in quarantine:
                cur.execute(
                    """INSERT INTO meta.agent_quarantine
                    (agent_name, execution_id, record_data, reason, confidence_score, status)
                    VALUES (%s, %s, %s, %s, %s, 'PENDING')""",
                    (
                        self.AGENT_NAME,
                        execution_id,
                        json.dumps(record.get("data", {})),
                        record.get("reason", "Low confidence"),
                        record.get("confidence_score", 0.0),
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Quarantined {len(quarantine)} records")

    def log_execution(
        self,
        execution_id: str,
        started_at: datetime,
        result: AgentResult,
        records_input: int,
    ) -> None:
        """Log execution to meta.agent_execution_log (append-only)."""
        completed_at = datetime.now(timezone.utc)
        status = "FAILED" if result.error else "COMPLETED"
        cost = self.estimated_cost_usd

        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meta.agent_execution_log
                (id, agent_name, agent_version, started_at, completed_at, status,
                 records_input, records_enriched, records_quarantined,
                 error_message, model_used, cost_usd)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    execution_id,
                    self.AGENT_NAME,
                    self.AGENT_VERSION,
                    started_at,
                    completed_at,
                    status,
                    records_input,
                    len(result.enriched),
                    len(result.quarantine),
                    result.error,
                    self.model,
                    round(cost, 6) if cost > 0 else None,
                ),
            )
        self.conn.commit()

        duration = (completed_at - started_at).total_seconds()
        cost_str = f", ${cost:.4f}" if cost > 0 else ""
        logger.info(
            f"[{self.AGENT_NAME}] {status}: "
            f"{len(result.enriched)} enriched, {len(result.quarantine)} quarantined "
            f"in {duration:.1f}s"
            f" ({self._total_input_tokens} in / {self._total_output_tokens} out tokens{cost_str})"
        )

        # Record Prometheus metrics for CMS agents
        try:
            from ..observability.metrics import record_cms_agent_execution
            record_cms_agent_execution(
                agent_name=self.AGENT_NAME,
                status=status.lower(),
                cost_usd=cost,
                quarantined=len(result.quarantine),
            )
        except Exception:
            pass  # metrics should never break agent execution

    def run(self) -> None:
        """Full execution: load → process → write → log."""
        execution_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)

        # Log start
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO meta.agent_execution_log
                (id, agent_name, agent_version, started_at, status, model_used)
                VALUES (%s, %s, %s, %s, 'RUNNING', %s)""",
                (execution_id, self.AGENT_NAME, self.AGENT_VERSION, started_at, self.model),
            )
        self.conn.commit()

        try:
            batch = self.load_batch()
            logger.info(f"[{self.AGENT_NAME}] Loaded {len(batch)} records")

            result = self.execute(batch)

            if result.enriched:
                self.write_results(result.enriched)
            if result.quarantine:
                self.write_quarantine(result.quarantine, execution_id)

            self.log_execution(execution_id, started_at, result, len(batch))

        except Exception as e:
            logger.exception(f"[{self.AGENT_NAME}] Failed: {e}")
            error_result = AgentResult(error=str(e))
            self.log_execution(execution_id, started_at, error_result, 0)
            raise
        finally:
            if self._conn and not self._conn.closed:
                self._conn.close()
