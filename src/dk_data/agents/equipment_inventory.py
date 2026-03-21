"""Equipment Inventory Agent.

Maps HCPCS codes from the CMS Outpatient PUF to equipment categories, building
a facility-level equipment inventory.  Results land in
hcs_silver.cms_equipment_inventory and hcs_silver.ref_hcpcs_equipment.
"""

import json
import logging
from typing import Any

from dk_data.agents.base_agent import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

FACILITY_BATCH_SIZE = 50  # facilities per load
HCPCS_CHUNK_SIZE = 100  # HCPCS codes per LLM call

SYSTEM_PROMPT = """\
You are a healthcare equipment and medical device specialist. Given HCPCS
(Healthcare Common Procedure Coding System) codes from outpatient claims data,
map each code to the medical equipment required to perform that procedure.

Equipment categories:
  MRI, CT Scanner, X-Ray, Ultrasound, PET Scanner, SPECT Scanner,
  Mammography, Fluoroscopy, C-Arm, Linear Accelerator, Gamma Knife,
  Lithotripter, Laser System, Endoscope, Arthroscope, Ventilator,
  Dialysis Machine, Cardiac Catheterization Lab, Electrophysiology Lab,
  Operating Room, Robotic Surgery System, Infusion Pump, Monitor,
  Laboratory Analyzer, Blood Bank Equipment, Pharmacy Automation, Other, None

For each HCPCS code, determine:
- equipment_category: Primary equipment category from the list above
- equipment_name: Specific equipment name if identifiable
- is_capital_equipment: Whether this is major capital equipment (true/false)
- typical_cost_range: Estimated cost range ("low" <$50k, "medium" $50k-$500k, "high" >$500k)

Respond with JSON:
{
  "mappings": [
    {
      "hcpcs_code": "<code>",
      "hcpcs_description": "<description>",
      "equipment_category": "<category>",
      "equipment_name": "<specific name>",
      "is_capital_equipment": true|false,
      "typical_cost_range": "low|medium|high",
      "confidence": <0.0-1.0>
    }
  ]
}
"""


class EquipmentInventoryAgent(BaseAgent):
    """Map HCPCS codes to equipment categories and build facility inventories."""

    AGENT_NAME = "equipment_inventory"
    AGENT_VERSION = "1.0.0"

    def load_batch(self) -> list[dict[str, Any]]:
        """Load outpatient HCPCS data for facilities not yet inventoried."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    op.ccn,
                    op.hcpcs_code,
                    op.hcpcs_description,
                    op.total_services
                FROM hcs_bronze.cms_outpatient_puf op
                LEFT JOIN hcs_silver.cms_equipment_inventory ei
                    ON op.ccn = ei.ccn AND op.hcpcs_code = ei.hcpcs_code
                WHERE ei.ccn IS NULL
                ORDER BY op.ccn, op.total_services DESC
                LIMIT %s
            """, (FACILITY_BATCH_SIZE * 20,))  # ~20 codes per facility
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, batch: list[dict[str, Any]]) -> AgentResult:
        """Map HCPCS codes to equipment via LLM, then build facility inventory."""
        if not batch:
            return AgentResult()

        enriched: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []

        # Deduplicate HCPCS codes for ref table mapping
        unique_hcpcs: dict[str, str] = {}
        for r in batch:
            if r["hcpcs_code"] not in unique_hcpcs:
                unique_hcpcs[r["hcpcs_code"]] = r.get("hcpcs_description", "")

        # Get equipment mappings for unique HCPCS codes
        hcpcs_mappings: dict[str, dict] = {}
        hcpcs_items = [
            {"hcpcs_code": code, "hcpcs_description": desc}
            for code, desc in unique_hcpcs.items()
        ]

        for i in range(0, len(hcpcs_items), HCPCS_CHUNK_SIZE):
            chunk = hcpcs_items[i : i + HCPCS_CHUNK_SIZE]

            try:
                response = self.call_llm([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"hcpcs_codes": chunk})},
                ])

                for m in response.get("mappings", []):
                    confidence = float(m.get("confidence", 0.0))
                    hcpcs_mappings[m["hcpcs_code"]] = {
                        "equipment_category": m.get("equipment_category", "Other"),
                        "equipment_name": m.get("equipment_name", ""),
                        "is_capital_equipment": bool(m.get("is_capital_equipment", False)),
                        "typical_cost_range": m.get("typical_cost_range", "low"),
                        "confidence_score": confidence,
                    }

            except Exception as exc:
                logger.error(f"LLM call failed for HCPCS chunk at index {i}: {exc}")
                for item in chunk:
                    quarantine.append({
                        "data": item,
                        "reason": f"LLM error: {exc}",
                        "confidence_score": 0.0,
                    })

        # Build facility-level inventory and ref records
        ref_records: list[dict[str, Any]] = []
        inventory_records: list[dict[str, Any]] = []

        # Ref table entries (deduplicated HCPCS -> equipment)
        for hcpcs_code, mapping in hcpcs_mappings.items():
            confidence = mapping["confidence_score"]
            ref_record = {
                "hcpcs_code": hcpcs_code,
                "hcpcs_description": unique_hcpcs.get(hcpcs_code, ""),
                "equipment_category": mapping["equipment_category"],
                "equipment_name": mapping["equipment_name"],
                "is_capital_equipment": mapping["is_capital_equipment"],
                "typical_cost_range": mapping["typical_cost_range"],
                "confidence_score": confidence,
                "agent_version": self.AGENT_VERSION,
                "_table": "ref_hcpcs_equipment",
            }

            if confidence >= self.CONFIDENCE_THRESHOLD_REVIEW:
                ref_records.append(ref_record)
            else:
                quarantine.append({
                    "data": ref_record,
                    "reason": f"Low confidence ({confidence:.2f})",
                    "confidence_score": confidence,
                })

        # Facility inventory entries
        for r in batch:
            mapping = hcpcs_mappings.get(r["hcpcs_code"])
            if not mapping:
                continue
            if mapping["equipment_category"] == "None":
                continue  # Skip codes that don't map to equipment

            confidence = mapping["confidence_score"]
            inv_record = {
                "ccn": r["ccn"],
                "hcpcs_code": r["hcpcs_code"],
                "equipment_category": mapping["equipment_category"],
                "equipment_name": mapping["equipment_name"],
                "total_services": r.get("total_services", 0),
                "confidence_score": confidence,
                "agent_version": self.AGENT_VERSION,
                "_table": "cms_equipment_inventory",
            }

            if confidence >= self.CONFIDENCE_THRESHOLD_REVIEW:
                inventory_records.append(inv_record)
            else:
                quarantine.append({
                    "data": inv_record,
                    "reason": f"Low confidence ({confidence:.2f})",
                    "confidence_score": confidence,
                })

        enriched = ref_records + inventory_records
        return AgentResult(enriched=enriched, quarantine=quarantine)

    def write_results(self, enriched: list[dict[str, Any]]) -> None:
        """Insert equipment mappings into both silver tables."""
        ref_count = 0
        inv_count = 0

        with self.conn.cursor() as cur:
            for r in enriched:
                table = r.pop("_table", None)

                if table == "ref_hcpcs_equipment":
                    cur.execute(
                        """INSERT INTO hcs_silver.ref_hcpcs_equipment
                        (hcpcs_code, hcpcs_description, equipment_category,
                         equipment_name, is_capital_equipment, typical_cost_range,
                         confidence_score, agent_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (hcpcs_code) DO UPDATE SET
                            equipment_category = EXCLUDED.equipment_category,
                            equipment_name = EXCLUDED.equipment_name,
                            is_capital_equipment = EXCLUDED.is_capital_equipment,
                            typical_cost_range = EXCLUDED.typical_cost_range,
                            confidence_score = EXCLUDED.confidence_score,
                            agent_version = EXCLUDED.agent_version
                        """,
                        (
                            r["hcpcs_code"],
                            r.get("hcpcs_description", ""),
                            r["equipment_category"],
                            r.get("equipment_name", ""),
                            r["is_capital_equipment"],
                            r.get("typical_cost_range", "low"),
                            r["confidence_score"],
                            r["agent_version"],
                        ),
                    )
                    ref_count += 1

                elif table == "cms_equipment_inventory":
                    cur.execute(
                        """INSERT INTO hcs_silver.cms_equipment_inventory
                        (ccn, hcpcs_code, equipment_category, equipment_name,
                         total_services, confidence_score, agent_version)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (ccn, hcpcs_code) DO UPDATE SET
                            equipment_category = EXCLUDED.equipment_category,
                            equipment_name = EXCLUDED.equipment_name,
                            total_services = EXCLUDED.total_services,
                            confidence_score = EXCLUDED.confidence_score,
                            agent_version = EXCLUDED.agent_version
                        """,
                        (
                            r["ccn"],
                            r["hcpcs_code"],
                            r["equipment_category"],
                            r.get("equipment_name", ""),
                            r.get("total_services", 0),
                            r["confidence_score"],
                            r["agent_version"],
                        ),
                    )
                    inv_count += 1

        self.conn.commit()
        logger.info(
            f"[{self.AGENT_NAME}] Wrote {ref_count} ref mappings + "
            f"{inv_count} inventory records"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    EquipmentInventoryAgent().run()
