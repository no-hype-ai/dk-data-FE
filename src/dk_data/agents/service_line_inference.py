"""Service Line Inference Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads DRG claim mix per NPI from hcs_bronze.cms_inpatient_puf and uses an LLM
to classify each provider's primary service line. Writes to hcs_silver.service_lines.

Confidence routing:
    < 0.5  → quarantine
    0.5–0.79 → needs_review = True
    >= 0.8 → direct write
"""

import asyncio
import json
import re
import sys
from typing import Any, Optional

import asyncpg
import structlog

from dk_data.agents.base_agent import BaseAgent, AgentResult, RunResult, MAX_EVIDENCE_PER_PILLAR

logger = structlog.get_logger(__name__)

SILVER_TABLE = "hcs_silver.service_lines"

SERVICE_LINE_PROMPT = """\
You are a healthcare analytics expert. Given the DRG (Diagnosis Related Group) claim mix
for a provider (NPI), classify the provider's PRIMARY service line.

NPI: {npi}
Top DRGs by claim volume:
{drg_summary}

Valid service lines:
- Cardiology
- Orthopedics
- Oncology
- Neurology
- General Surgery
- Obstetrics / Women's Health
- Psychiatry / Behavioral Health
- Gastroenterology
- Pulmonology / Critical Care
- Rehabilitation
- Primary Care / Internal Medicine
- Emergency Medicine
- Other

Respond ONLY with a JSON object, no additional text:
{{
  "service_line": "<service_line>",
  "rationale": "<1-2 sentence explanation>",
  "confidence_score": <float 0.0-1.0>
}}
"""


class ServiceLineInferenceAgent(BaseAgent):
    AGENT_NAME = "service_line_inference"
    SILVER_TABLE = SILVER_TABLE

    def _parse_confidence(self, llm_response: str) -> float:
        try:
            data = json.loads(llm_response)
            return float(data.get("confidence_score", 0.0))
        except Exception:
            match = re.search(r'"confidence_score"\s*:\s*([0-9.]+)', llm_response)
            if match:
                return float(match.group(1))
        return 0.0

    async def fetch_records(self, scope: Any, limit: int) -> list[dict]:
        """Fetch provider_ids + their DRG mix from hcs_bronze.cms_inpatient_puf.

        NOTE: cms_inpatient_puf uses CCN provider IDs (not NPIs). We store
        provider_id in the npi column of hcs_silver.service_lines as a pragmatic
        mapping — the silver table schema uses 'npi' as the key column.
        """
        db_pool = await self._get_db_pool()
        source_year: Optional[int] = scope if isinstance(scope, int) else None

        year_clause = "AND _source_year = $2" if source_year else ""
        args: list[Any] = [limit]
        if source_year:
            args.append(source_year)

        query = f"""
            SELECT
                provider_id,
                MAX(_source_year) AS source_year,
                jsonb_agg(
                    jsonb_build_object(
                        'drg_definition', drg_definition,
                        'total_discharges', total_discharges
                    )
                    ORDER BY total_discharges DESC
                ) AS drg_mix
            FROM hcs_bronze.cms_inpatient_puf
            WHERE provider_id IS NOT NULL
              AND provider_id NOT IN (
                  SELECT npi FROM hcs_silver.service_lines
              )
              {year_clause}
            GROUP BY provider_id
            HAVING COUNT(*) >= 3
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = []
        for row in rows:
            drg_mix = row["drg_mix"]
            if isinstance(drg_mix, str):
                drg_mix = json.loads(drg_mix)
            records.append({
                "id": row["provider_id"],
                "npi": row["provider_id"],  # stored as npi in silver table
                "source_year": row["source_year"],
                "drg_mix": drg_mix,
            })

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        npi = record["npi"]
        drg_mix = record.get("drg_mix", [])

        drg_summary = "\n".join(
            f"  DRG {d.get('drg_definition', 'UNK')}: "
            f"{d.get('total_discharges', 0)} discharges"
            for d in drg_mix[:20]
        )

        prompt = SERVICE_LINE_PROMPT.format(npi=npi, drg_summary=drg_summary)

        try:
            response_text, confidence = await self._call_llm_with_escalation(prompt, npi)
            parsed = json.loads(response_text)
            service_line = parsed.get("service_line", "Other")
            rationale = parsed.get("rationale", "")
        except Exception as e:
            return AgentResult(
                record_id=npi,
                success=False,
                error=str(e),
            )

        return AgentResult(
            record_id=npi,
            success=True,
            confidence_score=confidence,
            needs_review=confidence < 0.8,
            output={
                "npi": npi,
                "service_line": service_line,
                "confidence_score": confidence,
                "needs_review": confidence < 0.8,
                "agent_output": response_text,
                "source_year": record.get("source_year"),
                "rationale": rationale,
            },
        )

    async def write_results(
        self, results: list[AgentResult], db_pool: asyncpg.Pool
    ) -> int:
        written = 0
        async with db_pool.acquire() as conn:
            for result in results:
                if not result.success or not result.output:
                    continue
                o = result.output
                await conn.execute(
                    """
                    INSERT INTO hcs_silver.service_lines
                        (npi, service_line, confidence_score, needs_review,
                         agent_output, _source_year)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (npi) DO UPDATE SET
                        service_line = EXCLUDED.service_line,
                        confidence_score = EXCLUDED.confidence_score,
                        needs_review = EXCLUDED.needs_review,
                        agent_output = EXCLUDED.agent_output,
                        _source_year = EXCLUDED._source_year,
                        updated_at = NOW()
                    """,
                    o["npi"],
                    o["service_line"],
                    o["confidence_score"],
                    o["needs_review"],
                    o["agent_output"],
                    o["source_year"],
                )
                written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Service Line Inference Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=int, default=None, help="Source year filter")
    args = parser.parse_args()

    agent = ServiceLineInferenceAgent()
    result: RunResult = await agent.run(scope=args.scope, limit=args.limit)

    print(f"Agent: {result.agent_name}")
    print(f"  Processed : {result.records_processed}")
    print(f"  Written   : {result.records_written}")
    print(f"  Quarantined: {result.records_quarantined}")
    print(f"  Needs review: {result.records_needs_review}")
    print(f"  Status    : {result.status}")
    if result.errors:
        print(f"  Errors    : {result.errors[:5]}")

    sys.exit(0 if result.status == "success" else 1)


if __name__ == "__main__":
    asyncio.run(main())
