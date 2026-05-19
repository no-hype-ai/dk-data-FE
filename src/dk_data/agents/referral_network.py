"""Referral Network Inference Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads from hcs_raw.cms_referring_providers and hcs_raw.cms_ordering_providers,
infers referral strength and relationship type between provider pairs via LLM,
and writes to hcs_agents.referral_network.

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

SILVER_TABLE = "hcs_agents.referral_network"

REFERRAL_NETWORK_PROMPT = """\
You are a healthcare referral network analyst. Below is a summary of claim-level
co-occurrence data between a referring provider and a receiving provider.

Referring NPI : {referring_npi}
Receiving NPI : {receiving_npi}
Source year   : {source_year}
Referral volume (shared patients/claims): {referral_volume}
Service types observed: {service_types}

Based on this data, assess the strength and nature of this referral relationship.

Respond ONLY with a JSON object:
{{
  "relationship_strength": "strong|moderate|weak|incidental",
  "inferred_specialty_alignment": "<brief description>",
  "confidence_score": <float 0.0-1.0>,
  "rationale": "<1-2 sentences>"
}}
"""


class ReferralNetworkAgent(BaseAgent):
    AGENT_NAME = "referral_network"
    SILVER_TABLE = SILVER_TABLE

    def _parse_confidence(self, llm_response: str) -> float:
        try:
            data = json.loads(llm_response)
            return float(data.get("confidence_score", 0.0))
        except Exception:
            pass
        match = re.search(r'"confidence_score"\s*:\s*([0-9.]+)', llm_response)
        if match:
            return float(match.group(1))
        return 0.0

    async def fetch_records(self, scope: Any, limit: int) -> list[dict]:
        """Fetch provider pairs from cms_referring_providers.

        Uses hcs_raw.cms_referring_providers directly — it already has provider
        pairs (referring_npi + referred_to_npi) with referral_count. No join to
        cms_ordering_providers is needed; that table has a different schema.
        """
        db_pool = await self._get_db_pool()
        source_year: int | None = scope if isinstance(scope, int) else None
        year_clause = "AND r._source_year = $2" if source_year else ""
        args: list[Any] = [limit]
        if source_year:
            args.append(source_year)

        query = f"""
            SELECT
                r.referring_npi,
                r.referred_to_npi AS receiving_npi,
                r._source_year AS source_year,
                r.referral_count AS referral_volume,
                ARRAY[r.provider_type]::text[] AS service_types
            FROM hcs_raw.cms_referring_providers r
            WHERE r.referring_npi IS NOT NULL
              AND r.referred_to_npi IS NOT NULL
              AND r.referral_count >= 5
              AND NOT EXISTS (
                  SELECT 1 FROM hcs_agents.referral_network rn
                  WHERE rn.referring_npi = r.referring_npi
                    AND rn.receiving_npi = r.referred_to_npi
                    AND rn._source_year = r._source_year
              )
              {year_clause}
            ORDER BY r.referral_count DESC
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = [
            {
                "id": f"{row['referring_npi']}_to_{row['receiving_npi']}_{row['source_year']}",
                "referring_npi": row["referring_npi"],
                "receiving_npi": row["receiving_npi"],
                "source_year": row["source_year"],
                "referral_volume": row["referral_volume"],
                "service_types": list(row["service_types"]) if row["service_types"] else [],
            }
            for row in rows
        ]

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        record_id = record["id"]
        service_types_str = ", ".join(record.get("service_types") or []) or "Unknown"

        prompt = REFERRAL_NETWORK_PROMPT.format(
            referring_npi=record["referring_npi"],
            receiving_npi=record["receiving_npi"],
            source_year=record.get("source_year", "Unknown"),
            referral_volume=record["referral_volume"],
            service_types=service_types_str,
        )

        try:
            response_text, confidence = await self._call_llm_with_escalation(
                prompt, record_id
            )
            parsed = json.loads(response_text)
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
                "referring_npi": record["referring_npi"],
                "receiving_npi": record["receiving_npi"],
                "referral_volume": record["referral_volume"],
                "confidence_score": confidence,
                "needs_review": confidence < 0.8,
                "agent_output": response_text,
                "source_year": record.get("source_year"),
                "relationship_strength": parsed.get("relationship_strength", "unknown"),
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
                    INSERT INTO hcs_agents.referral_network
                        (referring_npi, receiving_npi, referral_volume,
                         relationship_strength, confidence_score, needs_review,
                         agent_output, _source_year)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (referring_npi, receiving_npi, _source_year) DO UPDATE SET
                        referral_volume = EXCLUDED.referral_volume,
                        relationship_strength = EXCLUDED.relationship_strength,
                        confidence_score = EXCLUDED.confidence_score,
                        needs_review = EXCLUDED.needs_review,
                        agent_output = EXCLUDED.agent_output,
                        updated_at = NOW()
                    """,
                    o["referring_npi"],
                    o["receiving_npi"],
                    o["referral_volume"],
                    o["relationship_strength"],
                    o["confidence_score"],
                    o["needs_review"],
                    o["agent_output"],
                    o["source_year"],
                )
                written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Referral Network Inference Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=int, default=None, help="Source year filter")
    args = parser.parse_args()

    agent = ReferralNetworkAgent()
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
