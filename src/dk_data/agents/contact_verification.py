"""Contact Verification Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads phone and address fields from hcs_raw.cms_nppes, validates and normalizes
contact information via LLM, and writes to hcs_silver.verified_contacts.

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

SILVER_TABLE = "hcs_silver.verified_contacts"

CONTACT_VERIFICATION_PROMPT = """\
You are a contact data quality specialist. Review the following raw contact information
for a healthcare provider (NPI) and normalize/validate it.

NPI: {npi}
Raw phone (practice): {phone_practice}
Raw phone (fax): {phone_fax}
Address line 1: {address_1}
Address line 2: {address_2}
City: {city}
State: {state}
ZIP: {zip_code}
Country: {country}
Entity type: {entity_type}

Tasks:
1. Normalize the phone number to E.164 format (+1XXXXXXXXXX for US) if valid.
2. Assess the address completeness and flag any anomalies.
3. Note: email is not available in NPPES raw data — set verified_email to null.
4. Assign a verification_status: "verified" | "normalized" | "suspect" | "invalid"
5. Assign confidence_score based on how complete and consistent the data appears.

Respond ONLY with a JSON object:
{{
  "verified_phone": "<E.164 phone or null>",
  "verified_email": null,
  "verification_status": "verified|normalized|suspect|invalid",
  "address_notes": "<brief note on address quality or null>",
  "confidence_score": <float 0.0-1.0>,
  "rationale": "<1-2 sentences>"
}}
"""


class ContactVerificationAgent(BaseAgent):
    AGENT_NAME = "contact_verification"
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
        """Fetch NPIs with contact info not yet in verified_contacts."""
        db_pool = await self._get_db_pool()
        state: str | None = scope if isinstance(scope, str) and scope else None
        state_clause = (
            "AND provider_business_practice_location_address_state_name = $2"
            if state
            else ""
        )
        args: list[Any] = [limit]
        if state:
            args.append(state)

        query = f"""
            SELECT
                npi,
                provider_business_practice_location_address_telephone_number AS phone_practice,
                provider_business_practice_location_address_fax_number AS phone_fax,
                provider_first_line_business_practice_location_address AS address_1,
                provider_second_line_business_practice_location_address AS address_2,
                provider_business_practice_location_address_city_name AS city,
                provider_business_practice_location_address_state_name AS state,
                provider_business_practice_location_address_postal_code AS zip_code,
                provider_business_practice_location_address_country_code AS country,
                entity_type_code AS entity_type
            FROM hcs_raw.cms_nppes
            WHERE npi IS NOT NULL
              AND npi NOT IN (SELECT npi FROM hcs_silver.verified_contacts)
              AND (
                  provider_business_practice_location_address_telephone_number IS NOT NULL
                  OR provider_first_line_business_practice_location_address IS NOT NULL
                  OR provider_business_practice_location_address_city_name IS NOT NULL
              )
              {state_clause}
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)

        records = [
            {
                "id": row["npi"],
                "npi": row["npi"],
                "phone_practice": row["phone_practice"] or "",
                "phone_fax": row["phone_fax"] or "",
                "address_1": row["address_1"] or "",
                "address_2": row["address_2"] or "",
                "city": row["city"] or "",
                "state": row["state"] or "",
                "zip_code": row["zip_code"] or "",
                "country": row["country"] or "US",
                "entity_type": row["entity_type"] or "",
            }
            for row in rows
        ]

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        npi = record["npi"]

        prompt = CONTACT_VERIFICATION_PROMPT.format(
            npi=npi,
            phone_practice=record["phone_practice"] or "Not provided",
            phone_fax=record["phone_fax"] or "Not provided",
            address_1=record["address_1"] or "Not provided",
            address_2=record["address_2"] or "",
            city=record["city"] or "Not provided",
            state=record["state"] or "Not provided",
            zip_code=record["zip_code"] or "Not provided",
            country=record["country"] or "US",
            entity_type=record["entity_type"] or "Unknown",
        )

        try:
            response_text, confidence = await self._call_llm_with_escalation(prompt, npi)
            parsed = json.loads(response_text)
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
                "verified_phone": parsed.get("verified_phone"),
                "verified_email": None,
                "verification_status": parsed.get("verification_status", "suspect"),
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
                await conn.execute(
                    """
                    INSERT INTO hcs_silver.verified_contacts
                        (npi, verified_phone, verified_email, verification_status,
                         confidence_score, needs_review, agent_output)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (npi) DO UPDATE SET
                        verified_phone = EXCLUDED.verified_phone,
                        verified_email = EXCLUDED.verified_email,
                        verification_status = EXCLUDED.verification_status,
                        confidence_score = EXCLUDED.confidence_score,
                        needs_review = EXCLUDED.needs_review,
                        agent_output = EXCLUDED.agent_output,
                        updated_at = NOW()
                    """,
                    o["npi"],
                    o["verified_phone"],
                    o["verified_email"],
                    o["verification_status"],
                    o["confidence_score"],
                    o["needs_review"],
                    o["agent_output"],
                )
                written += 1
        return written


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Contact Verification Agent")
    parser.add_argument("--limit", type=int, default=MAX_EVIDENCE_PER_PILLAR)
    parser.add_argument("--scope", type=str, default=None, help="State code filter (e.g. CA)")
    args = parser.parse_args()

    agent = ContactVerificationAgent()
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
