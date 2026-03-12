"""Service Line Inference Agent.

Classifies DRG codes into clinical service lines (Cardiology, Orthopedics,
Neurology, Oncology, etc.) using LLM inference over bronze CMS inpatient PUF
data.  Results land in silver.ref_drg_service_line.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # DRG codes per LLM call

SYSTEM_PROMPT = """\
You are a clinical coding expert. Given a list of DRG (Diagnosis Related Group)
codes and descriptions, classify each into exactly one clinical service line.

Valid service lines:
  Cardiology, Orthopedics, Neurology, Oncology, Pulmonology,
  Gastroenterology, Nephrology, Endocrinology, Infectious Disease,
  General Surgery, Vascular Surgery, Urology, OB/GYN,
  Psychiatry, Rehabilitation, Neonatology, Trauma, ENT,
  Ophthalmology, Dermatology, Hematology, Transplant, Other

Respond with JSON:
{
  "classifications": [
    {
      "drg_code": "<code>",
      "service_line": "<service_line>",
      "confidence": <0.0-1.0>
    }
  ]
}
"""


class ServiceLineInferenceAgent(BaseAgent):
    """Classify DRG codes into clinical service lines."""

    AGENT_NAME = "service_line_inference"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load DRG codes not yet classified."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ip.drg_code, ip.drg_description
                FROM bronze.cms_inpatient_puf ip
                LEFT JOIN silver.ref_drg_service_line sl
                    ON ip.drg_code = sl.drg_code
                WHERE sl.drg_code IS NULL
                ORDER BY ip.drg_code
            """)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Classify DRGs in sub-batches of BATCH_SIZE."""
        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        for i in range(0, len(batch), BATCH_SIZE):
            chunk = batch[i : i + BATCH_SIZE]
            items = [
                {"drg_code": r["drg_code"], "drg_description": r["drg_description"]}
                for r in chunk
            ]

            try:
                response = self.call_llm([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"drg_codes": items})},
                ])

                for cls in response.get("classifications", []):
                    confidence = float(cls.get("confidence", 0.0))
                    record = {
                        "drg_code": cls["drg_code"],
                        "drg_description": next(
                            (r["drg_description"] for r in chunk if r["drg_code"] == cls["drg_code"]),
                            "",
                        ),
                        "service_line": cls["service_line"],
                        "confidence_score": confidence,
                        "agent_version": self.AGENT_VERSION,
                    }

                    if confidence >= self.CONFIDENCE_THRESHOLD_ACCEPT:
                        record["review_status"] = "auto_accept"
                        enriched.append(record)
                    elif confidence >= self.CONFIDENCE_THRESHOLD_REVIEW:
                        record["review_status"] = "needs_review"
                        enriched.append(record)
                    else:
                        quarantine.append({
                            "data": record,
                            "reason": f"Low confidence ({confidence:.2f})",
                            "confidence_score": confidence,
                        })

            except Exception as exc:
                logger.error(f"LLM call failed for chunk starting at index {i}: {exc}")
                for r in chunk:
                    quarantine.append({
                        "data": r,
                        "reason": f"LLM error: {exc}",
                        "confidence_score": 0.0,
                    })

        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert classified DRG service lines into silver."""
        with self.conn.cursor() as cur:
            for r in enriched:
                cur.execute(
                    """INSERT INTO silver.ref_drg_service_line
                    (drg_code, drg_description, service_line, confidence_score, agent_version)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (drg_code) DO UPDATE SET
                        service_line = EXCLUDED.service_line,
                        confidence_score = EXCLUDED.confidence_score,
                        agent_version = EXCLUDED.agent_version
                    """,
                    (
                        r["drg_code"],
                        r["drg_description"],
                        r["service_line"],
                        r["confidence_score"],
                        r["agent_version"],
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Wrote {len(enriched)} service-line classifications")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ServiceLineInferenceAgent().run()
