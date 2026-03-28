"""Staffing Decomposition Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads staffing-related cost report fields from hcs_raw.cms_cost_reports_puf,
decomposes reported staffing into clinical role categories via LLM, and writes
to hcs_agents.staffing_decomposition.

Confidence routing:
    < 0.5  → quarantine
    0.5–0.79 → needs_review = True
    >= 0.8 → direct write
"""

import asyncio
import json
import re
import sys
from typing import Any

import asyncpg
import structlog

from dk_data.agents.base_agent import BaseAgent, AgentResult, RunResult, MAX_EVIDENCE_PER_PILLAR

logger = structlog.get_logger(__name__)

SILVER_TABLE = "hcs_agents.staffing_decomposition"

STAFFING_DECOMPOSITION_PROMPT = """\
You are a healthcare cost report analyst with expertise in CMS cost reports (Form CMS-2552).

Below are staffing-related cost report line items for a healthcare provider.
Decompose the total reported hours/FTEs into the most likely clinical role categories.

Provider ID : {provider_id}
Report Year : {source_year}
Facility type: {facility_type}

Cost report staffing line items:
{line_items}

Decompose into clinical role categories. For each identified category provide a JSON object.
Return a JSON array of role decompositions:
[
  {{
    "role_category": "<RN|LPN|CNA|MD/DO|NP/PA|Allied Health|Administrative|Support Staff|Other>",
    "fte_estimate": <float>,
    "evidence_line_items": ["<cost_report_line_ref>"],
    "confidence_score": <float 0.0-1.0>,
    "rationale": "<brief>"
  }}
]

Respond ONLY with the JSON array.
"""


class StaffingDecompositionAgent(BaseAgent):
    AGENT_NAME = "staffing_decomposition"
    SILVER_TABLE = SILVER_TABLE

    def _parse_confidence(self, llm_response: str) -> float:
        try:
            data = json.loads(llm_response)
            if isinstance(data, list) and data:
                scores = [
                    float(item.get("confidence_score", 0.0))
                    for item in data
                    if isinstance(item, dict)
                ]
                return min(scores) if scores else 0.0
        except Exception:
            pass
        match = re.search(r'"confidence_score"\s*:\s*([0-9.]+)', llm_response)
        if match:
            return float(match.group(1))
        return 0.0

    async def fetch_records(self, scope: Any, limit: int) -> list[dict]:
        """Fetch provider-level staffing aggregates from cms_cost_reports_puf_lines."""
        db_pool = await self._get_db_pool()
        source_year: int | None = scope if isinstance(scope, int) else None
        year_clause = "AND cr._source_year = $2" if source_year else ""
        args: list[Any] = [limit]
        if source_year:
            args.append(source_year)

        query = f"""
            SELECT
                cr.provider_id,
                MAX(cr._source_year) AS source_year,
                MAX(cr.facility_type) AS facility_type,
                jsonb_agg(
                    jsonb_build_object(
                        'line_item', cr.line_item_code,
                        'description', cr.line_item_description,
                        'hours_or_fte', cr.reported_hours_fte,
                        'salaries', cr.total_salaries
                    )
                    ORDER BY cr.line_item_code
                ) AS line_items
            FROM hcs_raw.cms_cost_reports_puf_lines cr
            WHERE cr.provider_id IS NOT NULL
              AND (cr.reported_hours_fte IS NOT NULL OR cr.total_salaries IS NOT NULL)
              AND cr.line_item_code LIKE 'A-%'
              AND cr.provider_id NOT IN (
                  SELECT DISTINCT provider_id FROM hcs_agents.staffing_decomposition
              )
              {year_clause}
            GROUP BY cr.provider_id
            HAVING COUNT(*) >= 2
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = []
        for row in rows:
            line_items = row["line_items"]
            if isinstance(line_items, str):
                line_items = json.loads(line_items)
            records.append({
                "id": f"{row['provider_id']}_{row['source_year']}",
                "provider_id": row["provider_id"],
                "source_year": row["source_year"],
                "facility_type": row["facility_type"] or "Unknown",
                "line_items": line_items,
            })

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        record_id = record["id"]
        line_items = record.get("line_items", [])

        line_items_str = "\n".join(
            f"  {li.get('line_item', 'UNK')} | {li.get('description', '')} | "
            f"FTE/Hours: {li.get('hours_or_fte', 'N/A')} | Salaries: ${li.get('salaries', 0):,.0f}"
            for li in line_items[:30]
        )

        prompt = STAFFING_DECOMPOSITION_PROMPT.format(
            provider_id=record["provider_id"],
            source_year=record.get("source_year", "Unknown"),
            facility_type=record.get("facility_type", "Unknown"),
            line_items=line_items_str,
        )

        try:
            response_text, confidence = await self._call_llm_with_escalation(
                prompt, record_id
            )
            parsed = json.loads(response_text)
            if not isinstance(parsed, list):
                raise ValueError("Expected JSON array from LLM")
        except Exception as e:
            return AgentResult(
                record_id=record_id,
                success=False,
                error=str(e),
            )

        return AgentResult(
            record_id=record_id,
            success=True,
            confidence_score=confidence,
            needs_review=confidence < 0.8,
            output={
                "provider_id": record["provider_id"],
                "source_year": record.get("source_year"),
                "decompositions": parsed,
                "confidence_score": confidence,
                "needs_review": confidence < 0.8,
                "agent_output": response_text,
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
                decompositions = o.get("decompositions", [])

                for decomp in decompositions:
                    if not isinstance(decomp, dict):
                        continue
                    role_confidence = float(decomp.get("confidence_score", o["confidence_score"]))
                    await conn.execute(
                        """
                        INSERT INTO hcs_agents.staffing_decomposition
                            (provider_id, role_category, fte_estimate,
                             confidence_score, needs_review, agent_output, _source_year)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (provider_id, role_category, _source_year) DO UPDATE SET
                            fte_estimate = EXCLUDED.fte_estimate,
                            confidence_score = EXCLUDED.confidence_score,
                            needs_review = EXCLUDED.needs_review,
                            agent_output = EXCLUDED.agent_output,
                            updated_at = NOW()
                        """,
                        o["provider_id"],
                        decomp.get("role_category", "Other"),
                        float(decomp.get("fte_estimate", 0.0)),
                        role_confidence,
                        o["needs_review"],
                        o["agent_output"],
                        o["source_year"],
                    )
                    written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Staffing Decomposition Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=int, default=None, help="Source year filter")
    args = parser.parse_args()

    agent = StaffingDecompositionAgent()
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
