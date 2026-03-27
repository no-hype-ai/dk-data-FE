"""Publication Evidence Extractor Agent.

Feature: 019-cms-puf-platform-reconciliation

Reads abstracts from silver.publications that are not yet staged in
mol_silver.publication_evidence_staging, extracts structured clinical endpoint
data via LLM, and writes to staging. A SQLMesh model promotes staging -> live.

Confidence routing:
    < 0.5  → quarantine (skips staging write)
    0.5–0.79 → staging write with needs_review = True
    >= 0.8 → staging write with needs_review = False

The live mol_silver.publication_evidence table is populated by the SQLMesh model
publication_evidence.sql, which runs @daily and promotes from staging where
confidence_score >= 0.40 and promoted_at IS NULL.
"""

import asyncio
import hashlib
import json
import re
import sys
from typing import Any, Optional

import asyncpg
import structlog

from dk_data.agents.base_agent import BaseAgent, AgentResult, RunResult, MAX_EVIDENCE_PER_PILLAR

logger = structlog.get_logger(__name__)

SILVER_TABLE = "mol_silver.publication_evidence_staging"

NCT_RE = re.compile(r'\bNCT\d{8}\b', re.IGNORECASE)

EXTRACTION_PROMPT = """\
You are a clinical trial data extraction specialist. Extract structured endpoint
data from the following publication abstract.

PMID  : {pmid}
DOI   : {doi}
Title : {title}
Abstract:
{abstract}

Extract the PRIMARY endpoint (or the most prominent endpoint if not specified).
Return ONLY a JSON object with exactly these fields:
{{
  "endpoint_name": "<endpoint name, e.g. 'Overall Survival', 'PFS', 'ORR'>",
  "endpoint_type": "primary|secondary|exploratory",
  "hazard_ratio": <float or null>,
  "p_value": <float or null>,
  "response_rate": <float 0.0-1.0 or null>,
  "median_survival_months": <float or null>,
  "sample_size": <integer or null>,
  "trial_nct_id": "<NCT number if mentioned, else null>",
  "confidence_score": <float 0.0-1.0, how confident you are in the extracted values>
}}

Rules:
- response_rate must be between 0.0 and 1.0 (convert percentages: 42% → 0.42)
- p_value must be a raw float (0.04, not "< 0.05" — use the numeric value if available, else null)
- If the abstract does not contain clinical endpoint data, set confidence_score to 0.1
- confidence_score reflects data completeness: 1.0 = all fields populated with high certainty
"""


def _compute_content_hash(pmid: int | str, endpoint_name: str) -> str:
    """MD5 hash of str(pmid) + endpoint_name, hex-encoded."""
    raw = str(pmid) + endpoint_name
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _extract_nct_from_text(text: str) -> Optional[str]:
    """Pull the first NCT number from free text, if present."""
    match = NCT_RE.search(text or "")
    return match.group(0).upper() if match else None


class PublicationEvidenceExtractorAgent(BaseAgent):
    AGENT_NAME = "publication_evidence_extractor"
    SILVER_TABLE = SILVER_TABLE

    def _parse_confidence(self, llm_response: str) -> float:
        """Parse confidence_score from JSON response."""
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
        """
        Fetch abstracts from silver.publications not yet in staging.

        Uses a LEFT JOIN on (pmid + endpoint_name hash) to detect new abstracts.
        Since the hash is computed at write time, we approximate by checking
        whether the pmid already has ANY staging entry at all. A more precise
        dedup happens via ON CONFLICT DO NOTHING at write time.
        """
        db_pool = await self._get_db_pool()

        query = """
            SELECT
                p.id,
                p.pmid,
                p.doi,
                p.title,
                p.abstract,
                p.publication_date
            FROM silver.publications p
            WHERE p.abstract IS NOT NULL
              AND LENGTH(TRIM(p.abstract)) > 100
              AND p.pmid IS NOT NULL
              AND p.pmid NOT IN (
                  SELECT DISTINCT pmid
                  FROM mol_silver.publication_evidence_staging
              )
            ORDER BY p.publication_date DESC NULLS LAST
            LIMIT $1
        """

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, limit)

        records = [
            {
                "id": str(row["pmid"]),
                "db_id": row["id"],
                "pmid": row["pmid"],
                "doi": row["doi"],
                "title": row["title"] or "",
                "abstract": row["abstract"],
                "publication_date": row["publication_date"],
            }
            for row in rows
        ]

        logger.info("fetched_records", agent=self.AGENT_NAME, count=len(records))
        return records

    async def _process_single(self, record: dict) -> AgentResult:
        pmid = record["pmid"]
        record_id = str(pmid)

        # Also try to find NCT IDs in the abstract directly
        nct_from_abstract = _extract_nct_from_text(record.get("abstract", ""))

        prompt = EXTRACTION_PROMPT.format(
            pmid=pmid,
            doi=record.get("doi") or "Not available",
            title=record.get("title") or "Not available",
            abstract=record["abstract"],
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

        endpoint_name = parsed.get("endpoint_name") or "Unknown Endpoint"
        content_hash = _compute_content_hash(pmid, endpoint_name)

        # Prefer NCT from LLM response; fall back to regex from abstract
        trial_nct_id = parsed.get("trial_nct_id") or nct_from_abstract

        return AgentResult(
            record_id=record_id,
            success=True,
            confidence_score=confidence,
            needs_review=confidence < 0.8,
            output={
                "content_hash": content_hash,
                "molecule_id": None,           # not linked at extraction stage
                "trial_nct_id": trial_nct_id,
                "pmid": pmid,
                "doi": record.get("doi"),
                "endpoint_name": endpoint_name,
                "endpoint_type": parsed.get("endpoint_type", "primary"),
                "hazard_ratio": _to_float(parsed.get("hazard_ratio")),
                "p_value": _to_float(parsed.get("p_value")),
                "response_rate": _clamp_rate(parsed.get("response_rate")),
                "median_survival_months": _to_float(parsed.get("median_survival_months")),
                "sample_size": _to_int(parsed.get("sample_size")),
                "confidence_score": confidence,
                "needs_review": confidence < 0.8,
                "agent_output": response_text,
            },
        )

    async def write_results(
        self, results: list[AgentResult], db_pool: asyncpg.Pool
    ) -> int:
        """
        Write to mol_silver.publication_evidence_staging.
        ON CONFLICT DO NOTHING — content_hash is the dedup key.
        """
        written = 0
        async with db_pool.acquire() as conn:
            for result in results:
                if not result.success or not result.output:
                    continue
                o = result.output
                await conn.execute(
                    """
                    INSERT INTO mol_silver.publication_evidence_staging (
                        content_hash,
                        molecule_id,
                        trial_nct_id,
                        pmid,
                        doi,
                        endpoint_name,
                        endpoint_type,
                        hazard_ratio,
                        p_value,
                        response_rate,
                        median_survival_months,
                        sample_size,
                        confidence_score,
                        needs_review,
                        staged_at,
                        promoted_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, NOW(), NULL
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    o["content_hash"],
                    o["molecule_id"],
                    o["trial_nct_id"],
                    o["pmid"],
                    o["doi"],
                    o["endpoint_name"],
                    o["endpoint_type"],
                    o["hazard_ratio"],
                    o["p_value"],
                    o["response_rate"],
                    o["median_survival_months"],
                    o["sample_size"],
                    o["confidence_score"],
                    o["needs_review"],
                )
                written += 1
        return written


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_rate(value: Any) -> Optional[float]:
    """Ensure response_rate is 0.0–1.0; convert >1 as percentage."""
    f = _to_float(value)
    if f is None:
        return None
    if f > 1.0:
        f = f / 100.0
    return max(0.0, min(1.0, f))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Publication Evidence Extractor Agent")
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_EVIDENCE_PER_PILLAR,
        help="Max abstracts to process per run (default: 50)",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Optional scope (unused; reserved for molecule_id or date filter)",
    )
    args = parser.parse_args()

    agent = PublicationEvidenceExtractorAgent()
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
