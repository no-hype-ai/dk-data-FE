"""Staffing Decomposition Agent.

Parses HCRIS (Hospital Cost Report Information System) worksheet line items
into structured staffing categories including FTE counts, salary costs, benefits,
and contract labor.  Results land in silver.cms_staffing_profiles.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

FACILITY_BATCH_SIZE = 20  # facilities per LLM call
RELEVANT_WORKSHEETS = ("S-3", "A", "A-6")

SYSTEM_PROMPT = """\
You are a healthcare finance analyst expert in CMS Hospital Cost Reports (HCRIS).

Given HCRIS line items from worksheets S-3 (Hospital Statistics), A (Cost
Allocation — General Service Categories), and A-6 (Reclassifications), decompose
them into staffing categories.

Standard staffing categories:
  Nursing, Physician, Allied Health, Administrative, Technician,
  Dietary, Housekeeping, Maintenance, Social Services, Pharmacy,
  Respiratory Therapy, Physical Therapy, Lab, Radiology, Other

For each facility (identified by CCN), produce staffing profile entries with:
- staffing_category: One of the standard categories above
- fte_count: Full-time equivalent staff count (from S-3 data)
- salary_cost: Total salary cost in USD
- benefits_cost: Benefits cost in USD
- contract_labor_cost: Contract/agency labor cost in USD

Respond with JSON:
{
  "staffing_profiles": [
    {
      "ccn": "<facility CCN>",
      "staffing_category": "<category>",
      "fte_count": <number or null>,
      "salary_cost": <number or null>,
      "benefits_cost": <number or null>,
      "contract_labor_cost": <number or null>,
      "confidence": <0.0-1.0>,
      "source_lines": ["<worksheet:line:col>"]
    }
  ]
}
"""


class StaffingDecompositionAgent(BaseAgent):
    """Decompose HCRIS line items into staffing categories."""

    AGENT_NAME = "staffing_decomposition"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load HCRIS data for facilities not yet profiled."""
        with self.conn.cursor() as cur:
            # First get CCNs that need processing
            cur.execute("""
                SELECT DISTINCT h.ccn
                FROM bronze.cms_hcris h
                LEFT JOIN silver.cms_staffing_profiles sp ON h.ccn = sp.ccn
                WHERE h.worksheet IN %s
                  AND sp.ccn IS NULL
                ORDER BY h.ccn
                LIMIT %s
            """, (RELEVANT_WORKSHEETS, FACILITY_BATCH_SIZE))
            ccns = [row[0] for row in cur.fetchall()]

            if not ccns:
                return []

            # Load all relevant line items for those facilities
            cur.execute("""
                SELECT ccn, worksheet, line_number, column_number, value
                FROM bronze.cms_hcris
                WHERE ccn = ANY(%s)
                  AND worksheet IN %s
                ORDER BY ccn, worksheet, line_number, column_number
            """, (ccns, RELEVANT_WORKSHEETS))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Parse HCRIS line items into staffing profiles via LLM."""
        if not batch:
            return AgentResult()

        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        # Group by CCN for coherent facility-level analysis
        facilities: dict[str, list[dict]] = {}
        for r in batch:
            ccn = r["ccn"]
            facilities.setdefault(ccn, []).append(r)

        # Process in sub-batches of facilities
        ccn_list = list(facilities.keys())
        for i in range(0, len(ccn_list), FACILITY_BATCH_SIZE):
            chunk_ccns = ccn_list[i : i + FACILITY_BATCH_SIZE]
            chunk_data = {ccn: facilities[ccn] for ccn in chunk_ccns}

            # Convert Decimal/numeric types for JSON serialization
            serializable = {}
            for ccn, rows in chunk_data.items():
                serializable[ccn] = [
                    {k: (float(v) if hasattr(v, "__float__") and k == "value" else v)
                     for k, v in row.items()}
                    for row in rows
                ]

            try:
                response = self.call_llm([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"facilities": serializable})},
                ])

                for profile in response.get("staffing_profiles", []):
                    confidence = float(profile.get("confidence", 0.0))
                    record = {
                        "ccn": profile["ccn"],
                        "staffing_category": profile["staffing_category"],
                        "fte_count": profile.get("fte_count"),
                        "salary_cost": profile.get("salary_cost"),
                        "benefits_cost": profile.get("benefits_cost"),
                        "contract_labor_cost": profile.get("contract_labor_cost"),
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
                            "reason": f"Low confidence ({confidence:.2f})",
                            "confidence_score": confidence,
                        })

            except Exception as exc:
                logger.error(f"LLM call failed for staffing chunk at index {i}: {exc}")
                for ccn in chunk_ccns:
                    quarantine.append({
                        "data": {"ccn": ccn, "line_count": len(facilities[ccn])},
                        "reason": f"LLM error: {exc}",
                        "confidence_score": 0.0,
                    })

        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert staffing profiles into silver."""
        with self.conn.cursor() as cur:
            for r in enriched:
                cur.execute(
                    """INSERT INTO silver.cms_staffing_profiles
                    (ccn, staffing_category, fte_count, salary_cost,
                     benefits_cost, contract_labor_cost,
                     confidence_score, agent_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ccn, staffing_category) DO UPDATE SET
                        fte_count = EXCLUDED.fte_count,
                        salary_cost = EXCLUDED.salary_cost,
                        benefits_cost = EXCLUDED.benefits_cost,
                        contract_labor_cost = EXCLUDED.contract_labor_cost,
                        confidence_score = EXCLUDED.confidence_score,
                        agent_version = EXCLUDED.agent_version
                    """,
                    (
                        r["ccn"],
                        r["staffing_category"],
                        r.get("fte_count"),
                        r.get("salary_cost"),
                        r.get("benefits_cost"),
                        r.get("contract_labor_cost"),
                        r["confidence_score"],
                        r["agent_version"],
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Wrote {len(enriched)} staffing profiles")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    StaffingDecompositionAgent().run()
