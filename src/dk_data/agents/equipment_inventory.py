"""Equipment Inventory Inference Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads HCPCS procedure codes from hcs_raw.cms_physician_puf, infers equipment
categories from observed HCPCS patterns via LLM, and writes to
hcs_silver.equipment_inventory.

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

SILVER_TABLE = "hcs_silver.equipment_inventory"

EQUIPMENT_INVENTORY_PROMPT = """\
You are a healthcare equipment and technology specialist. Based on a provider's
observed HCPCS procedure codes, infer what medical equipment categories they
likely possess or use regularly.

NPI: {npi}
Source year: {source_year}

Top HCPCS codes by service volume:
{hcpcs_summary}

Identify equipment categories implied by these HCPCS codes. For each category, provide:
{{
  "equipment_category": "<category name>",
  "hcpcs_evidence": ["<code1>", "<code2>"],
  "inferred_equipment": "<specific equipment or technology>",
  "confidence_score": <float 0.0-1.0>,
  "rationale": "<1-2 sentences>"
}}

Examples of equipment categories: Cardiac Cath Lab, Surgical Robot, MRI/CT Scanner,
ECMO, Endoscopy Suite, Radiation Therapy, Dialysis, Infusion Pump, Ventilator Bank,
Interventional Radiology, PET Scanner, TAVR Program, Stereotactic Surgery.

Return a JSON array of identified equipment categories.
Respond ONLY with the JSON array.
"""


class EquipmentInventoryAgent(BaseAgent):
    AGENT_NAME = "equipment_inventory"
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
        """Fetch NPIs + HCPCS code mix from cms_physician_puf_services."""
        db_pool = await self._get_db_pool()
        source_year: int | None = scope if isinstance(scope, int) else None
        year_clause = "AND _source_year = $2" if source_year else ""
        args: list[Any] = [limit]
        if source_year:
            args.append(source_year)

        query = f"""
            SELECT
                npi,
                MAX(_source_year) AS source_year,
                jsonb_agg(
                    jsonb_build_object(
                        'hcpcs_code', hcpcs_code,
                        'hcpcs_description', hcpcs_description,
                        'line_srvc_cnt', line_srvc_cnt,
                        'place_of_service', place_of_service
                    )
                    ORDER BY line_srvc_cnt DESC
                ) AS hcpcs_mix
            FROM hcs_raw.cms_physician_puf_services
            WHERE npi IS NOT NULL
              AND hcpcs_code IS NOT NULL
              AND npi NOT IN (
                  SELECT DISTINCT npi FROM hcs_silver.equipment_inventory
              )
              {year_clause}
            GROUP BY npi
            HAVING COUNT(DISTINCT hcpcs_code) >= 5
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = []
        for row in rows:
            hcpcs_mix = row["hcpcs_mix"]
            if isinstance(hcpcs_mix, str):
                hcpcs_mix = json.loads(hcpcs_mix)
            records.append({
                "id": f"{row['npi']}_{row['source_year']}",
                "npi": row["npi"],
                "source_year": row["source_year"],
                "hcpcs_mix": hcpcs_mix,
            })

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        record_id = record["id"]
        hcpcs_mix = record.get("hcpcs_mix", [])

        hcpcs_summary = "\n".join(
            f"  {h.get('hcpcs_code', 'UNK')} ({h.get('hcpcs_description', '')}) "
            f"— {h.get('line_srvc_cnt', 0):,} services, POS: {h.get('place_of_service', 'N/A')}"
            for h in hcpcs_mix[:25]
        )

        prompt = EQUIPMENT_INVENTORY_PROMPT.format(
            npi=record["npi"],
            source_year=record.get("source_year", "Unknown"),
            hcpcs_summary=hcpcs_summary,
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
                "npi": record["npi"],
                "source_year": record.get("source_year"),
                "equipment_items": parsed,
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
                for item in o.get("equipment_items", []):
                    if not isinstance(item, dict):
                        continue
                    item_confidence = float(
                        item.get("confidence_score", o["confidence_score"])
                    )
                    hcpcs_evidence = json.dumps(item.get("hcpcs_evidence", []))
                    await conn.execute(
                        """
                        INSERT INTO hcs_silver.equipment_inventory
                            (npi, equipment_category, hcpcs_evidence, inferred_equipment,
                             confidence_score, needs_review, agent_output, _source_year)
                        VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8)
                        ON CONFLICT (npi, equipment_category, _source_year) DO UPDATE SET
                            hcpcs_evidence = EXCLUDED.hcpcs_evidence,
                            inferred_equipment = EXCLUDED.inferred_equipment,
                            confidence_score = EXCLUDED.confidence_score,
                            needs_review = EXCLUDED.needs_review,
                            agent_output = EXCLUDED.agent_output,
                            updated_at = NOW()
                        """,
                        o["npi"],
                        item.get("equipment_category", "Other"),
                        hcpcs_evidence,
                        item.get("inferred_equipment"),
                        item_confidence,
                        o["needs_review"],
                        o["agent_output"],
                        o["source_year"],
                    )
                    written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Equipment Inventory Inference Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=int, default=None, help="Source year filter")
    args = parser.parse_args()

    agent = EquipmentInventoryAgent()
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
