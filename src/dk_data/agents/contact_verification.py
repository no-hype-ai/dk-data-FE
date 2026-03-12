"""Contact Verification Agent.

Validates and normalizes provider contact information (phone numbers and
addresses) from the CMS NPPES registry using LLM analysis.  Results land in
silver.cms_verified_contacts.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # NPIs per load
LLM_CHUNK_SIZE = 100  # records per LLM call

SYSTEM_PROMPT = """\
You are a data-quality specialist for US healthcare provider contact records.

For each provider record, perform the following validations:

1. **Phone**: Normalize to E.164 format (+1XXXXXXXXXX). Flag as invalid if the
   number has fewer than 10 digits, uses a known invalid area code (e.g. 000,
   555), or is otherwise malformed.

2. **Address**: Check for completeness (street, city, state, ZIP). Normalize
   state to 2-letter code. Validate ZIP is 5 or 9 digits. Flag as invalid if
   critical fields are missing or clearly fake (e.g. "123 Test St").

3. **Geocode inference**: From the validated address, extract state and ZIP for
   geocoding reference.

Respond with JSON:
{
  "verifications": [
    {
      "npi": "<npi>",
      "phone_normalized": "<+1XXXXXXXXXX or null>",
      "phone_valid": true|false,
      "address_normalized": "<full normalized address or null>",
      "address_valid": true|false,
      "geocode_state": "<2-letter state>",
      "geocode_zip": "<5-digit ZIP>",
      "confidence": <0.0-1.0>,
      "issues": ["<issue description>"]
    }
  ]
}
"""


class ContactVerificationAgent(BaseAgent):
    """Validate and normalize provider contact information."""

    AGENT_NAME = "contact_verification"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load provider contacts not yet verified."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    n.npi,
                    n.phone,
                    n.practice_address,
                    n.mailing_address
                FROM bronze.cms_nppes n
                LEFT JOIN silver.cms_verified_contacts vc ON n.npi = vc.npi
                WHERE vc.npi IS NULL
                ORDER BY n.npi
                LIMIT %s
            """, (BATCH_SIZE,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Validate contacts in sub-batches via LLM."""
        if not batch:
            return AgentResult()

        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        for i in range(0, len(batch), LLM_CHUNK_SIZE):
            chunk = batch[i : i + LLM_CHUNK_SIZE]

            try:
                response = self.call_llm([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"providers": chunk})},
                ])

                for v in response.get("verifications", []):
                    confidence = float(v.get("confidence", 0.0))
                    record = {
                        "npi": v["npi"],
                        "phone_normalized": v.get("phone_normalized"),
                        "phone_valid": bool(v.get("phone_valid", False)),
                        "address_normalized": v.get("address_normalized"),
                        "address_valid": bool(v.get("address_valid", False)),
                        "geocode_state": v.get("geocode_state"),
                        "geocode_zip": v.get("geocode_zip"),
                        "confidence_score": confidence,
                        "agent_version": self.AGENT_VERSION,
                    }

                    if confidence >= self.CONFIDENCE_THRESHOLD_ACCEPT:
                        enriched.append(record)
                    elif confidence >= self.CONFIDENCE_THRESHOLD_REVIEW:
                        record["review_status"] = "needs_review"
                        enriched.append(record)
                    else:
                        quarantine.append({
                            "data": record,
                            "reason": f"Low confidence ({confidence:.2f}): {', '.join(v.get('issues', []))}",
                            "confidence_score": confidence,
                        })

            except Exception as exc:
                logger.error(f"LLM call failed for contact chunk at index {i}: {exc}")
                for r in chunk:
                    quarantine.append({
                        "data": r,
                        "reason": f"LLM error: {exc}",
                        "confidence_score": 0.0,
                    })

        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert verified contacts into silver."""
        with self.conn.cursor() as cur:
            for r in enriched:
                cur.execute(
                    """INSERT INTO silver.cms_verified_contacts
                    (npi, phone_normalized, phone_valid, address_normalized,
                     address_valid, geocode_state, geocode_zip,
                     confidence_score, agent_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (npi) DO UPDATE SET
                        phone_normalized = EXCLUDED.phone_normalized,
                        phone_valid = EXCLUDED.phone_valid,
                        address_normalized = EXCLUDED.address_normalized,
                        address_valid = EXCLUDED.address_valid,
                        geocode_state = EXCLUDED.geocode_state,
                        geocode_zip = EXCLUDED.geocode_zip,
                        confidence_score = EXCLUDED.confidence_score,
                        agent_version = EXCLUDED.agent_version
                    """,
                    (
                        r["npi"],
                        r.get("phone_normalized"),
                        r["phone_valid"],
                        r.get("address_normalized"),
                        r["address_valid"],
                        r.get("geocode_state"),
                        r.get("geocode_zip"),
                        r["confidence_score"],
                        r["agent_version"],
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Wrote {len(enriched)} verified contacts")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ContactVerificationAgent().run()
