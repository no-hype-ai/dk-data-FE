"""
Data Coverage API Routes.

Implements T042: Coverage score endpoint.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from ...services.ground_truth.coverage_service import CoverageService


router = APIRouter(prefix="/api/v1/coverage", tags=["coverage"])


# Response Models
class SourceCoverageResponse(BaseModel):
    """Coverage details for a data source."""
    source_name: str
    category: str
    is_available: bool
    completeness: float
    record_count: int
    last_updated: Optional[str]
    quality_score: float
    critical: bool


class CategoryScoreResponse(BaseModel):
    """Score for a data category."""
    category: str
    score: float
    sources_available: int
    sources_total: int
    critical_sources_missing: list


class CoverageResponse(BaseModel):
    """Data sufficiency score response."""
    drug_id: str
    drug_name: str
    overall_score: float
    overall_status: str
    category_scores: dict
    sources: dict
    missing_critical: list
    missing_optional: list
    recommendations: list
    assessed_at: str


class CoverageGapResponse(BaseModel):
    """Coverage gap details."""
    source: str
    category: str
    severity: str
    description: str
    remediation: str
    estimated_effort: str


class CoverageReportResponse(BaseModel):
    """Full coverage report."""
    drug_id: str
    drug_name: str
    sufficiency_score: CoverageResponse
    gaps: list
    data_freshness: dict
    comparison_to_peers: Optional[dict]
    generated_at: str


# Dependency
def get_coverage_service() -> CoverageService:
    """Get coverage service instance."""
    return CoverageService()


@router.get("/{molecule_id}", response_model=CoverageResponse)
async def get_coverage(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookups"),
    check_all_sources: bool = Query(default=True, description="Check all sources or critical only"),
):
    """
    Get data sufficiency score for a molecule.

    Checks data availability across multiple sources:

    **Critical Sources:**
    - FDA Approvals (OpenFDA)
    - ClinicalTrials.gov
    - FAERS (Adverse Events)
    - Orange Book (Patents)

    **Optional Sources:**
    - PubMed Publications
    - PatentsView
    - EMA (European)
    - Health Canada

    Returns:
    - **overall_score**: 0-100 score indicating data completeness
    - **overall_status**: excellent (90+), good (70-89), fair (50-69), poor (1-49), missing (0)
    - **category_scores**: Breakdown by category (regulatory, clinical, safety, etc.)
    - **recommendations**: Suggestions for improving coverage
    """
    logger.info(f"Getting coverage for {molecule_name} ({molecule_id})")

    try:
        service = get_coverage_service()
        score = await service.calculate_coverage(
            drug_id=molecule_id,
            drug_name=molecule_name,
            check_all_sources=check_all_sources,
        )

        result = score.to_dict()

        return CoverageResponse(
            drug_id=result["drug_id"],
            drug_name=result["drug_name"],
            overall_score=result["overall_score"],
            overall_status=result["overall_status"],
            category_scores=result["category_scores"],
            sources=result["sources"],
            missing_critical=result["missing_critical"],
            missing_optional=result["missing_optional"],
            recommendations=result["recommendations"],
            assessed_at=result["assessed_at"],
        )

    except Exception as e:
        logger.error(f"Coverage calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{molecule_id}/report", response_model=CoverageReportResponse)
async def get_coverage_report(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookups"),
):
    """
    Get full coverage report with gaps and remediation suggestions.

    Returns a comprehensive report including:
    - Data sufficiency score with breakdown
    - Identified coverage gaps with severity
    - Remediation suggestions for each gap
    - Data freshness timestamps
    - Comparison to peer molecules (if available)
    """
    logger.info(f"Generating coverage report for {molecule_name}")

    try:
        service = get_coverage_service()
        report = await service.generate_coverage_report(
            drug_id=molecule_id,
            drug_name=molecule_name,
        )

        result = report.to_dict()

        return CoverageReportResponse(
            drug_id=result["drug_id"],
            drug_name=result["drug_name"],
            sufficiency_score=CoverageResponse(
                drug_id=result["sufficiency_score"]["drug_id"],
                drug_name=result["sufficiency_score"]["drug_name"],
                overall_score=result["sufficiency_score"]["overall_score"],
                overall_status=result["sufficiency_score"]["overall_status"],
                category_scores=result["sufficiency_score"]["category_scores"],
                sources=result["sufficiency_score"]["sources"],
                missing_critical=result["sufficiency_score"]["missing_critical"],
                missing_optional=result["sufficiency_score"]["missing_optional"],
                recommendations=result["sufficiency_score"]["recommendations"],
                assessed_at=result["sufficiency_score"]["assessed_at"],
            ),
            gaps=result["gaps"],
            data_freshness=result["data_freshness"],
            comparison_to_peers=result.get("comparison_to_peers"),
            generated_at=result["generated_at"],
        )

    except Exception as e:
        logger.error(f"Coverage report generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{molecule_id}/gaps")
async def get_coverage_gaps(
    molecule_id: str,
    molecule_name: str = Query(..., description="Molecule name for lookups"),
    severity: Optional[str] = Query(default=None, description="Filter by severity: critical, high, medium, low"),
):
    """
    Get identified data coverage gaps.

    Returns gaps in data coverage with:
    - Severity level (critical, high, medium, low)
    - Affected data category
    - Description of the gap
    - Remediation suggestions
    - Estimated effort to resolve
    """
    logger.info(f"Getting coverage gaps for {molecule_name}")

    try:
        service = get_coverage_service()
        report = await service.generate_coverage_report(
            drug_id=molecule_id,
            drug_name=molecule_name,
        )

        gaps = [g.to_dict() for g in report.gaps]

        # Filter by severity if specified
        if severity:
            gaps = [g for g in gaps if g["severity"] == severity]

        return {
            "drug_id": molecule_id,
            "drug_name": molecule_name,
            "gaps": gaps,
            "total_count": len(gaps),
            "by_severity": {
                "critical": sum(1 for g in gaps if g["severity"] == "critical"),
                "high": sum(1 for g in gaps if g["severity"] == "high"),
                "medium": sum(1 for g in gaps if g["severity"] == "medium"),
                "low": sum(1 for g in gaps if g["severity"] == "low"),
            }
        }

    except Exception as e:
        logger.error(f"Gap analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
async def compare_coverage(
    molecule_ids: list = Query(..., description="List of molecule IDs to compare"),
    molecule_names: list = Query(..., description="List of molecule names (same order as IDs)"),
):
    """
    Compare data coverage across multiple molecules.

    Useful for identifying which molecules have the most complete data
    and which may need additional data collection.
    """
    if len(molecule_ids) != len(molecule_names):
        raise HTTPException(
            status_code=400,
            detail="molecule_ids and molecule_names must have same length"
        )

    if len(molecule_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 molecules can be compared at once"
        )

    logger.info(f"Comparing coverage for {len(molecule_ids)} molecules")

    try:
        service = get_coverage_service()
        results = []

        for drug_id, drug_name in zip(molecule_ids, molecule_names):
            score = await service.calculate_coverage(
                drug_id=drug_id,
                drug_name=drug_name,
                check_all_sources=True,
            )
            results.append({
                "drug_id": drug_id,
                "drug_name": drug_name,
                "overall_score": score.overall_score,
                "overall_status": score.overall_status.value,
                "missing_critical_count": len(score.missing_critical),
            })

        # Sort by score descending
        results.sort(key=lambda x: x["overall_score"], reverse=True)

        return {
            "molecules": results,
            "count": len(results),
            "average_score": sum(r["overall_score"] for r in results) / len(results),
            "best_coverage": results[0] if results else None,
            "worst_coverage": results[-1] if results else None,
        }

    except Exception as e:
        logger.error(f"Coverage comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
