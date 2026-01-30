"""Scoring Validation Agent.

Uses Claude AI to validate and explain TRS scoring calculations,
identify anomalies, and provide recommendations.
"""

import os
import logging
import json
from typing import Optional, List
from dataclasses import dataclass
from enum import Enum

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def get_anthropic_client() -> anthropic.Anthropic:
    """Get Anthropic client with API key from environment."""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


class AnomalyType(str, Enum):
    """Types of scoring anomalies."""
    SCORE_TOO_HIGH = "score_too_high"
    SCORE_TOO_LOW = "score_too_low"
    MISSING_DATA = "missing_data"
    INCONSISTENT = "inconsistent"
    OUTLIER = "outlier"
    TIER_MISMATCH = "tier_mismatch"


class ScoringAnomaly(BaseModel):
    """Detected anomaly in scoring."""
    anomaly_type: AnomalyType
    domain: str
    description: str
    severity: str = Field(description="low, medium, high")
    recommendation: str


class ScoringValidationResult(BaseModel):
    """Result of scoring validation."""
    hospital_id: str
    hospital_name: str
    is_valid: bool
    anomalies: List[ScoringAnomaly] = Field(default_factory=list)
    explanation: str
    recommendations: List[str] = Field(default_factory=list)
    confidence: float


@dataclass
class HospitalScoreContext:
    """Context for score validation."""
    hospital_id: str
    hospital_name: str
    state: str
    total_trs: int
    tier: str
    clinical_readiness_score: int
    operational_readiness_score: int
    strategic_alignment_score: int
    financial_capacity_score: int
    champion_access_score: int
    data_completeness: float
    tavr_volume: Optional[int] = None
    has_certification: Optional[bool] = None
    bed_count: Optional[int] = None
    operating_margin: Optional[float] = None


class ScoringValidationAgent:
    """AI agent for validating and explaining TRS scores.

    Uses Claude to analyze scoring patterns, identify anomalies,
    and provide explanations for score calculations.
    """

    SYSTEM_PROMPT = """You are a healthcare analytics expert specializing in hospital scoring systems.
You are validating Target Readiness Scores (TRS) for TAVR clinic targeting.

TRS scoring breakdown:
- Clinical Readiness: 0-250 points (TAVR volume, certification, quality rating, growth)
- Operational Readiness: 0-250 points (bed count, hospital type, emergency services, ownership)
- Strategic Alignment: 0-200 points (network tier, market priority, HPSA status, rural bonus)
- Financial Capacity: 0-150 points (operating margin, margin quartile)
- Champion Access: 0-150 points (health system presence, EMR system)
- Total: 0-1000 points

Tier classification:
- A: 800+ points (top targets)
- B: 600-799 points (strong candidates)
- C: 400-599 points (moderate potential)
- D: 200-399 points (lower priority)
- E: <200 points (not recommended)

When validating scores:
1. Check if domain scores are proportional to underlying data
2. Identify anomalies (too high, too low, inconsistent)
3. Explain the reasoning behind the score
4. Provide actionable recommendations

Respond with valid JSON matching the requested schema."""

    VALIDATION_PROMPT = """Validate the TRS scoring for this hospital:

Hospital: {hospital_name} ({hospital_id})
Location: {state}
Tier: {tier}
Total TRS: {total_trs}/1000

Domain Scores:
- Clinical Readiness: {clinical_readiness_score}/250
- Operational Readiness: {operational_readiness_score}/250
- Strategic Alignment: {strategic_alignment_score}/200
- Financial Capacity: {financial_capacity_score}/150
- Champion Access: {champion_access_score}/150

Data Completeness: {data_completeness:.1%}

Key Data Points:
- TAVR Volume: {tavr_volume}
- Has TVC Certification: {has_certification}
- Bed Count: {bed_count}
- Operating Margin: {operating_margin}

Analyze this scoring and provide:
1. is_valid: Whether the scoring appears reasonable (true/false)
2. anomalies: List of detected anomalies with type, domain, description, severity, recommendation
3. explanation: 2-3 sentence explanation of the overall score
4. recommendations: List of actionable recommendations
5. confidence: Your confidence in this validation (0.0-1.0)

Respond with a valid JSON object only."""

    BATCH_ANALYSIS_PROMPT = """Analyze scoring patterns across these hospitals:

{hospitals_summary}

Identify:
1. Common patterns in high-scoring (Tier A/B) hospitals
2. Common issues in low-scoring (Tier D/E) hospitals
3. Potential data quality issues affecting scores
4. Recommendations for improving scoring accuracy

Respond with a structured analysis."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize the scoring validation agent.

        Args:
            model: Claude model to use for validation.
        """
        self.model = model
        self.client = None

    def _ensure_client(self) -> None:
        """Ensure Anthropic client is initialized."""
        if self.client is None:
            self.client = get_anthropic_client()

    def validate_score(
        self,
        context: HospitalScoreContext
    ) -> ScoringValidationResult:
        """Validate a single hospital's TRS score.

        Args:
            context: Hospital score context.

        Returns:
            Validation result with anomalies and recommendations.
        """
        self._ensure_client()

        prompt = self.VALIDATION_PROMPT.format(
            hospital_id=context.hospital_id,
            hospital_name=context.hospital_name,
            state=context.state,
            tier=context.tier,
            total_trs=context.total_trs,
            clinical_readiness_score=context.clinical_readiness_score,
            operational_readiness_score=context.operational_readiness_score,
            strategic_alignment_score=context.strategic_alignment_score,
            financial_capacity_score=context.financial_capacity_score,
            champion_access_score=context.champion_access_score,
            data_completeness=context.data_completeness,
            tavr_volume=context.tavr_volume or "Unknown",
            has_certification=context.has_certification,
            bed_count=context.bed_count or "Unknown",
            operating_margin=f"{context.operating_margin:.1%}" if context.operating_margin else "Unknown"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract JSON from response
            content = response.content[0].text
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            # Parse anomalies
            anomalies = []
            for a in data.get('anomalies', []):
                try:
                    anomalies.append(ScoringAnomaly(
                        anomaly_type=AnomalyType(a.get('type', a.get('anomaly_type', 'inconsistent'))),
                        domain=a.get('domain', 'unknown'),
                        description=a.get('description', ''),
                        severity=a.get('severity', 'low'),
                        recommendation=a.get('recommendation', '')
                    ))
                except (ValueError, KeyError):
                    continue

            return ScoringValidationResult(
                hospital_id=context.hospital_id,
                hospital_name=context.hospital_name,
                is_valid=data.get('is_valid', True),
                anomalies=anomalies,
                explanation=data.get('explanation', ''),
                recommendations=data.get('recommendations', []),
                confidence=data.get('confidence', 0.5)
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return ScoringValidationResult(
                hospital_id=context.hospital_id,
                hospital_name=context.hospital_name,
                is_valid=True,
                explanation="Validation failed due to parsing error",
                confidence=0.0
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def validate_batch(
        self,
        contexts: List[HospitalScoreContext],
        flag_anomalies_only: bool = True
    ) -> List[ScoringValidationResult]:
        """Validate a batch of hospital scores.

        Args:
            contexts: List of hospital score contexts.
            flag_anomalies_only: Only return results with anomalies.

        Returns:
            List of validation results.
        """
        results = []

        for context in contexts:
            try:
                logger.info(f"Validating score for: {context.hospital_name}")
                result = self.validate_score(context)

                if not flag_anomalies_only or result.anomalies:
                    results.append(result)
                    logger.info(
                        f"Validated {context.hospital_id}: "
                        f"{'VALID' if result.is_valid else 'ISSUES FOUND'}"
                    )

            except Exception as e:
                logger.error(f"Failed to validate {context.hospital_id}: {e}")

        return results

    def analyze_scoring_patterns(
        self,
        contexts: List[HospitalScoreContext]
    ) -> str:
        """Analyze scoring patterns across multiple hospitals.

        Args:
            contexts: List of hospital score contexts.

        Returns:
            Analysis text with patterns and recommendations.
        """
        self._ensure_client()

        # Create summary for analysis
        tier_groups = {'A': [], 'B': [], 'C': [], 'D': [], 'E': []}
        for ctx in contexts:
            tier_groups[ctx.tier].append(ctx)

        summary_lines = []
        for tier in ['A', 'B', 'C', 'D', 'E']:
            hospitals = tier_groups[tier]
            if hospitals:
                avg_score = sum(h.total_trs for h in hospitals) / len(hospitals)
                avg_completeness = sum(h.data_completeness for h in hospitals) / len(hospitals)
                summary_lines.append(
                    f"Tier {tier}: {len(hospitals)} hospitals, "
                    f"avg TRS={avg_score:.0f}, "
                    f"avg completeness={avg_completeness:.1%}"
                )

        hospitals_summary = "\n".join(summary_lines)

        prompt = self.BATCH_ANALYSIS_PROMPT.format(
            hospitals_summary=hospitals_summary
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            return f"Analysis failed: {e}"


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    agent = ScoringValidationAgent()

    # Test with a sample hospital
    test_context = HospitalScoreContext(
        hospital_id="030064",
        hospital_name="Banner University Medical Center",
        state="AZ",
        total_trs=825,
        tier="A",
        clinical_readiness_score=210,
        operational_readiness_score=200,
        strategic_alignment_score=160,
        financial_capacity_score=130,
        champion_access_score=125,
        data_completeness=0.85,
        tavr_volume=285,
        has_certification=True,
        bed_count=650,
        operating_margin=0.08
    )

    result = agent.validate_score(test_context)
    print(json.dumps(result.model_dump(), indent=2, default=str))
