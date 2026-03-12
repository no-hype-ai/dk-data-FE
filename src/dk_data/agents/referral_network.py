"""Referral Network Agent.

Identifies and classifies provider-to-provider referral relationships by
analyzing overlapping HCPCS utilization and beneficiary patterns from the
CMS Physician & Other Suppliers PUF.  Results land in silver.cms_referral_edges.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

PAIR_BATCH_SIZE = 200  # provider pairs per LLM call

SYSTEM_PROMPT = """\
You are a healthcare referral-network analyst. Given pairs of providers with
their overlapping HCPCS codes and shared beneficiary counts, classify the
likely referral relationship between each pair.

Relationship types:
- "referral": Provider A regularly refers patients to Provider B
- "co-management": Both providers co-manage the same patients
- "same_practice": Providers likely share a practice / group
- "specialist_consult": One provider consults the other for specialist opinion
- "ancillary": One provider orders services from the other (lab, imaging)
- "none": No meaningful clinical relationship detected

For each pair, provide:
- relationship_type: One of the above
- strength_score: 0.0-1.0 indicating relationship strength
- confidence: 0.0-1.0 in your classification

Respond with JSON:
{
  "relationships": [
    {
      "source_npi": "<npi>",
      "target_npi": "<npi>",
      "relationship_type": "<type>",
      "strength_score": <0.0-1.0>,
      "confidence": <0.0-1.0>,
      "reasoning": "<brief explanation>"
    }
  ]
}
"""


class ReferralNetworkAgent(BaseAgent):
    """Classify referral relationships between provider pairs."""

    AGENT_NAME = "referral_network"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load provider pairs with overlapping HCPCS and beneficiaries."""
        with self.conn.cursor() as cur:
            cur.execute("""
                WITH provider_hcpcs AS (
                    SELECT
                        npi,
                        hcpcs_code,
                        total_beneficiaries,
                        total_services
                    FROM bronze.cms_physician_puf
                ),
                overlapping_pairs AS (
                    SELECT
                        a.npi AS source_npi,
                        b.npi AS target_npi,
                        COUNT(DISTINCT a.hcpcs_code) AS shared_hcpcs_count,
                        SUM(LEAST(a.total_beneficiaries, b.total_beneficiaries)) AS shared_patient_estimate
                    FROM provider_hcpcs a
                    JOIN provider_hcpcs b
                        ON a.hcpcs_code = b.hcpcs_code
                        AND a.npi < b.npi
                    GROUP BY a.npi, b.npi
                    HAVING COUNT(DISTINCT a.hcpcs_code) >= 3
                )
                SELECT
                    op.source_npi,
                    op.target_npi,
                    op.shared_hcpcs_count,
                    op.shared_patient_estimate
                FROM overlapping_pairs op
                LEFT JOIN silver.cms_referral_edges re
                    ON op.source_npi = re.source_npi
                    AND op.target_npi = re.target_npi
                WHERE re.source_npi IS NULL
                ORDER BY op.shared_patient_estimate DESC
                LIMIT %s
            """, (PAIR_BATCH_SIZE,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Classify each provider pair via LLM."""
        if not batch:
            return AgentResult()

        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        # Process in sub-batches of 50 pairs for manageable prompt size
        sub_batch_size = 50
        for i in range(0, len(batch), sub_batch_size):
            chunk = batch[i : i + sub_batch_size]
            serializable = []
            for r in chunk:
                row = {k: (int(v) if isinstance(v, (int, float)) and k != "shared_patient_estimate" else v)
                       for k, v in r.items()}
                serializable.append(row)

            try:
                response = self.call_llm([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"provider_pairs": serializable})},
                ])

                for rel in response.get("relationships", []):
                    confidence = float(rel.get("confidence", 0.0))
                    # Find original pair data for shared_patient_count
                    pair_data = next(
                        (p for p in chunk
                         if str(p["source_npi"]) == str(rel["source_npi"])
                         and str(p["target_npi"]) == str(rel["target_npi"])),
                        {},
                    )
                    record = {
                        "source_npi": rel["source_npi"],
                        "target_npi": rel["target_npi"],
                        "relationship_type": rel["relationship_type"],
                        "strength_score": float(rel.get("strength_score", 0.0)),
                        "shared_patient_count": pair_data.get("shared_patient_estimate", 0),
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
                            "reason": f"Low confidence ({confidence:.2f}): {rel.get('reasoning', '')}",
                            "confidence_score": confidence,
                        })

            except Exception as exc:
                logger.error(f"LLM call failed for referral chunk at index {i}: {exc}")
                for r in chunk:
                    quarantine.append({
                        "data": r,
                        "reason": f"LLM error: {exc}",
                        "confidence_score": 0.0,
                    })

        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert referral edges into silver."""
        with self.conn.cursor() as cur:
            for r in enriched:
                cur.execute(
                    """INSERT INTO silver.cms_referral_edges
                    (source_npi, target_npi, relationship_type, strength_score,
                     shared_patient_count, confidence_score, agent_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_npi, target_npi) DO UPDATE SET
                        relationship_type = EXCLUDED.relationship_type,
                        strength_score = EXCLUDED.strength_score,
                        shared_patient_count = EXCLUDED.shared_patient_count,
                        confidence_score = EXCLUDED.confidence_score,
                        agent_version = EXCLUDED.agent_version
                    """,
                    (
                        r["source_npi"],
                        r["target_npi"],
                        r["relationship_type"],
                        r["strength_score"],
                        r["shared_patient_count"],
                        r["confidence_score"],
                        r["agent_version"],
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Wrote {len(enriched)} referral edges")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ReferralNetworkAgent().run()
