"""Hospital Enrichment Agent.

Uses Claude AI to extract structured data from unstructured sources
for hospital enrichment (health system affiliation, EMR system, etc.)
"""

import os
import logging
import json
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Anthropic client initialization
def get_anthropic_client() -> anthropic.Anthropic:
    """Get Anthropic client with API key from environment."""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


class HospitalEnrichmentData(BaseModel):
    """Structured enrichment data extracted by AI agent."""
    health_system_name: Optional[str] = Field(
        None,
        description="Parent health system or network name"
    )
    emr_system: Optional[str] = Field(
        None,
        description="Electronic Medical Record system (Epic, Cerner, Meditech, etc.)"
    )
    academic_affiliation: Optional[str] = Field(
        None,
        description="University or medical school affiliation"
    )
    cardiac_surgery_program: Optional[bool] = Field(
        None,
        description="Whether hospital has cardiac surgery program"
    )
    cath_lab_count: Optional[int] = Field(
        None,
        description="Number of cardiac catheterization labs"
    )
    structural_heart_team: Optional[bool] = Field(
        None,
        description="Whether hospital has dedicated structural heart team"
    )
    confidence_score: float = Field(
        0.0,
        description="Confidence in extracted data (0-1)"
    )
    sources_used: List[str] = Field(
        default_factory=list,
        description="Sources used for extraction"
    )


@dataclass
class HospitalContext:
    """Hospital context for enrichment queries."""
    hospital_id: str
    hospital_name: str
    city: str
    state: str
    hospital_type: Optional[str] = None
    bed_count: Optional[int] = None


class HospitalEnrichmentAgent:
    """AI agent for hospital data enrichment.

    Uses Claude to extract structured information about hospitals
    from web searches and unstructured data sources.
    """

    SYSTEM_PROMPT = """You are a healthcare data analyst specializing in hospital information.
Your task is to extract structured data about hospitals from available information.

When given a hospital name and location, provide accurate information about:
1. Health system affiliation (parent organization, network)
2. EMR/EHR system used (Epic, Cerner, Meditech, Allscripts, etc.)
3. Academic affiliations (university medical centers, teaching hospitals)
4. Cardiac program details (surgery program, cath labs, structural heart team)

Guidelines:
- Only provide information you are confident about
- Indicate your confidence level (0-1) based on data quality
- List the types of sources you would use (public filings, press releases, etc.)
- If uncertain, leave fields as null rather than guessing
- Focus on verifiable, factual information

Output your response as a JSON object matching the requested schema."""

    EXTRACTION_PROMPT = """Extract enrichment data for the following hospital:

Hospital ID: {hospital_id}
Hospital Name: {hospital_name}
Location: {city}, {state}
Hospital Type: {hospital_type}
Bed Count: {bed_count}

Based on your knowledge of this hospital, provide:
1. health_system_name: Parent health system or network (null if independent)
2. emr_system: EMR/EHR system used (Epic, Cerner, Meditech, etc.)
3. academic_affiliation: University or medical school affiliation (null if none)
4. cardiac_surgery_program: Whether they have cardiac surgery (true/false/null)
5. cath_lab_count: Number of cath labs (integer or null)
6. structural_heart_team: Whether they have structural heart team (true/false/null)
7. confidence_score: Your confidence in this data (0.0-1.0)
8. sources_used: Types of sources this data would come from

Respond with a valid JSON object only."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize the enrichment agent.

        Args:
            model: Claude model to use for extraction.
        """
        self.model = model
        self.client = None

    def _ensure_client(self) -> None:
        """Ensure Anthropic client is initialized."""
        if self.client is None:
            self.client = get_anthropic_client()

    def enrich_hospital(
        self,
        hospital: HospitalContext
    ) -> HospitalEnrichmentData:
        """Enrich a single hospital with AI-extracted data.

        Args:
            hospital: Hospital context for enrichment.

        Returns:
            Extracted enrichment data.
        """
        self._ensure_client()

        prompt = self.EXTRACTION_PROMPT.format(
            hospital_id=hospital.hospital_id,
            hospital_name=hospital.hospital_name,
            city=hospital.city,
            state=hospital.state,
            hospital_type=hospital.hospital_type or "Unknown",
            bed_count=hospital.bed_count or "Unknown"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract JSON from response
            content = response.content[0].text
            # Clean up response if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())
            return HospitalEnrichmentData(**data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return HospitalEnrichmentData(
                confidence_score=0.0,
                sources_used=["extraction_failed"]
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during enrichment: {e}")
            return HospitalEnrichmentData(
                confidence_score=0.0,
                sources_used=["error"]
            )

    def enrich_batch(
        self,
        hospitals: List[HospitalContext],
        min_confidence: float = 0.5
    ) -> Dict[str, HospitalEnrichmentData]:
        """Enrich a batch of hospitals.

        Args:
            hospitals: List of hospitals to enrich.
            min_confidence: Minimum confidence threshold to accept results.

        Returns:
            Dictionary mapping hospital_id to enrichment data.
        """
        results = {}

        for hospital in hospitals:
            try:
                logger.info(f"Enriching hospital: {hospital.hospital_name}")
                enrichment = self.enrich_hospital(hospital)

                if enrichment.confidence_score >= min_confidence:
                    results[hospital.hospital_id] = enrichment
                    logger.info(
                        f"Enriched {hospital.hospital_id} with confidence "
                        f"{enrichment.confidence_score:.2f}"
                    )
                else:
                    logger.info(
                        f"Skipping {hospital.hospital_id}: low confidence "
                        f"({enrichment.confidence_score:.2f})"
                    )

            except Exception as e:
                logger.error(f"Failed to enrich {hospital.hospital_id}: {e}")

        return results


def update_staging_hospitals(
    enrichments: Dict[str, HospitalEnrichmentData]
) -> int:
    """Update staging.hospitals with enrichment data.

    Args:
        enrichments: Dictionary of hospital_id to enrichment data.

    Returns:
        Number of records updated.
    """
    # Import here to avoid circular dependency
    import sys
    sys.path.insert(0, str(__file__).rsplit('/claude_sdk', 1)[0])
    from ingestion.utils.database import get_connection

    updated = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for hospital_id, data in enrichments.items():
                try:
                    cur.execute("""
                        UPDATE staging.hospitals
                        SET health_system_name = COALESCE(%s, health_system_name),
                            emr_system = COALESCE(%s, emr_system),
                            _updated_at = NOW()
                        WHERE hospital_id = %s
                    """, (
                        data.health_system_name,
                        data.emr_system,
                        hospital_id
                    ))

                    if cur.rowcount > 0:
                        updated += 1

                except Exception as e:
                    logger.error(f"Failed to update {hospital_id}: {e}")

        conn.commit()

    logger.info(f"Updated {updated} hospital records with enrichment data")
    return updated


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    agent = HospitalEnrichmentAgent()

    # Test with a sample hospital
    test_hospital = HospitalContext(
        hospital_id="030064",
        hospital_name="Banner University Medical Center",
        city="Phoenix",
        state="AZ",
        hospital_type="Acute Care Hospitals",
        bed_count=650
    )

    result = agent.enrich_hospital(test_hospital)
    print(json.dumps(asdict(result) if hasattr(result, '__dataclass_fields__') else result.model_dump(), indent=2))
