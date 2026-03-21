"""IDN Hierarchy Agent.

Infers health-system organizational hierarchies from CMS PECOS enrollment and
Change of Ownership (CHOW) data using LLM analysis.  Results land in
hcs_silver.cms_health_system_hierarchy.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # organizations per LLM call

SYSTEM_PROMPT = """\
You are a healthcare industry analyst specializing in Integrated Delivery
Networks (IDNs) and health system corporate structures.

Given a batch of organizations with their ownership records (from CMS PECOS
enrollment and Change-of-Ownership filings), infer the organizational hierarchy.

For each organization determine:
- system_name: The name of the top-level health system it belongs to
- parent_system_id: The CCN or enrollment ID of its direct parent (null if top-level)
- hierarchy_level: "system" (top), "subsidiary", "facility", or "department"
- member_ccns: List of CCNs that are members under this entity (empty list if leaf)

Respond with JSON:
{
  "hierarchies": [
    {
      "system_id": "<ccn_or_enrollment_id>",
      "system_name": "<inferred system name>",
      "parent_system_id": null,
      "member_ccns": ["<ccn1>", "<ccn2>"],
      "hierarchy_level": "system|subsidiary|facility|department",
      "confidence": <0.0-1.0>,
      "reasoning": "<brief explanation>"
    }
  ]
}
"""


class IDNHierarchyAgent(BaseAgent):
    """Infer IDN organizational hierarchies from ownership data."""

    AGENT_NAME = "idn_hierarchy"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load organizations from PECOS + CHOW not yet in hierarchy table."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.enrollment_id,
                    p.ccn,
                    p.organization_name,
                    p.organization_type,
                    p.state,
                    c.old_owner_name,
                    c.new_owner_name,
                    c.change_date
                FROM hcs_bronze.cms_pecos p
                LEFT JOIN hcs_bronze.cms_chow c ON p.ccn = c.ccn
                LEFT JOIN hcs_silver.cms_health_system_hierarchy h ON p.ccn = h.system_id
                WHERE h.system_id IS NULL
                ORDER BY p.organization_name
                LIMIT %s
            """, (BATCH_SIZE,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Ask LLM to infer hierarchy for the batch."""
        if not batch:
            return AgentResult()

        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        # Serialize dates for JSON
        serializable = []
        for r in batch:
            row = dict(r)
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    row[k] = v.isoformat()
            serializable.append(row)

        try:
            response = self.call_llm([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"organizations": serializable})},
            ])

            for h in response.get("hierarchies", []):
                confidence = float(h.get("confidence", 0.0))
                record = {
                    "system_id": h["system_id"],
                    "system_name": h["system_name"],
                    "parent_system_id": h.get("parent_system_id"),
                    "member_ccns": h.get("member_ccns", []),
                    "hierarchy_level": h["hierarchy_level"],
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
                        "reason": f"Low confidence ({confidence:.2f}): {h.get('reasoning', '')}",
                        "confidence_score": confidence,
                    })

        except Exception as exc:
            logger.error(f"LLM call failed for IDN hierarchy batch: {exc}")
            for r in batch:
                quarantine.append({
                    "data": r,
                    "reason": f"LLM error: {exc}",
                    "confidence_score": 0.0,
                })

        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert hierarchy records into silver."""
        with self.conn.cursor() as cur:
            for r in enriched:
                cur.execute(
                    """INSERT INTO hcs_silver.cms_health_system_hierarchy
                    (system_id, system_name, parent_system_id, member_ccns,
                     hierarchy_level, confidence_score, agent_version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (system_id) DO UPDATE SET
                        system_name = EXCLUDED.system_name,
                        parent_system_id = EXCLUDED.parent_system_id,
                        member_ccns = EXCLUDED.member_ccns,
                        hierarchy_level = EXCLUDED.hierarchy_level,
                        confidence_score = EXCLUDED.confidence_score,
                        agent_version = EXCLUDED.agent_version
                    """,
                    (
                        r["system_id"],
                        r["system_name"],
                        r.get("parent_system_id"),
                        json.dumps(r.get("member_ccns", [])),
                        r["hierarchy_level"],
                        r["confidence_score"],
                        r["agent_version"],
                    ),
                )
        self.conn.commit()
        logger.info(f"[{self.AGENT_NAME}] Wrote {len(enriched)} hierarchy records")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    IDNHierarchyAgent().run()
