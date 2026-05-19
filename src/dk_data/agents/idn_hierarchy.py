"""IDN Hierarchy Inference Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads organization names and addresses from hcs_raw.cms_nppes, groups
geographically similar names, and infers Integrated Delivery Network (IDN)
parent-child relationships via LLM. Writes to hcs_agents.idn_hierarchy.

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

SILVER_TABLE = "hcs_agents.idn_hierarchy"

IDN_HIERARCHY_PROMPT = """\
You are a healthcare network analyst specializing in Integrated Delivery Networks (IDNs).

Below is a group of healthcare organizations that share a geographic area and have
similar names. Your task is to determine whether these organizations form an IDN
and, if so, identify the parent organization and the relationship type for each member.

Organizations:
{org_list}

For each child organization listed, respond with a JSON array. Each element must have:
{{
  "child_npi": "<NPI>",
  "parent_organization": "<parent org name or null if standalone>",
  "relationship_type": "subsidiary|affiliate|member|standalone",
  "confidence_score": <float 0.0-1.0>,
  "rationale": "<brief explanation>"
}}

Respond ONLY with the JSON array.
"""


class IDNHierarchyAgent(BaseAgent):
    AGENT_NAME = "idn_hierarchy"
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
        """Fetch geographic clusters of similarly named organizations from cms_nppes."""
        db_pool = await self._get_db_pool()
        state: str | None = scope if isinstance(scope, str) and scope else None
        state_clause = "AND provider_business_mailing_address_state_name = $2" if state else ""
        args: list[Any] = [limit]
        if state:
            args.append(state)

        # Group NPIs by (state, city, name prefix) to find candidate IDN clusters.
        # Each "record" is a geographic cluster of organizations.
        query = f"""
            SELECT
                provider_business_mailing_address_state_name AS state,
                provider_business_mailing_address_city_name AS city,
                LEFT(
                    LOWER(TRIM(provider_organization_name)), 12
                ) AS name_prefix,
                COUNT(*) AS org_count,
                jsonb_agg(
                    jsonb_build_object(
                        'npi', npi,
                        'org_name', provider_organization_name,
                        'city', provider_business_mailing_address_city_name,
                        'state', provider_business_mailing_address_state_name,
                        'zip', provider_business_mailing_address_postal_code,
                        'entity_type', entity_type_code
                    )
                ) AS members
            FROM hcs_raw.cms_nppes
            WHERE provider_organization_name IS NOT NULL
              AND entity_type_code = '2'
              AND npi NOT IN (SELECT child_npi FROM hcs_agents.idn_hierarchy)
              {state_clause}
            GROUP BY 1, 2, 3
            HAVING COUNT(*) BETWEEN 2 AND 30
            ORDER BY org_count DESC
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = []
        for i, row in enumerate(rows):
            members = row["members"]
            if isinstance(members, str):
                members = json.loads(members)
            records.append({
                "id": f"{row['state']}_{row['city']}_{row['name_prefix']}_{i}",
                "state": row["state"],
                "city": row["city"],
                "name_prefix": row["name_prefix"],
                "members": members,
            })

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        record_id = record["id"]
        members = record.get("members", [])

        org_list = "\n".join(
            f"  NPI: {m.get('npi')} | {m.get('org_name')} | "
            f"{m.get('city')}, {m.get('state')} {m.get('zip') or ''}".rstrip()
            for m in members
        )

        prompt = IDN_HIERARCHY_PROMPT.format(org_list=org_list)

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
                "cluster_id": record_id,
                "inferences": parsed,
                "confidence_score": confidence,
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
                inferences = result.output.get("inferences", [])
                overall_confidence = result.output["confidence_score"]
                agent_output = result.output["agent_output"]
                needs_review = result.needs_review

                for inf in inferences:
                    if not isinstance(inf, dict):
                        continue
                    child_npi = inf.get("child_npi")
                    if not child_npi:
                        continue
                    row_confidence = float(inf.get("confidence_score", overall_confidence))
                    await conn.execute(
                        """
                        INSERT INTO hcs_agents.idn_hierarchy
                            (child_npi, parent_organization, relationship_type,
                             confidence_score, needs_review, agent_output)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (child_npi) DO UPDATE SET
                            parent_organization = EXCLUDED.parent_organization,
                            relationship_type = EXCLUDED.relationship_type,
                            confidence_score = EXCLUDED.confidence_score,
                            needs_review = EXCLUDED.needs_review,
                            agent_output = EXCLUDED.agent_output,
                            updated_at = NOW()
                        """,
                        child_npi,
                        inf.get("parent_organization"),
                        inf.get("relationship_type", "standalone"),
                        row_confidence,
                        needs_review,
                        agent_output,
                    )
                    written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="IDN Hierarchy Inference Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=str, default=None, help="State code filter (e.g. CA)")
    args = parser.parse_args()

    agent = IDNHierarchyAgent()
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
