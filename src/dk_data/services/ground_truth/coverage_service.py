"""
Data Coverage Service.

Implements T041: DataSufficiencyScore calculation for molecules.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from ...models.coverage import (
    DataSufficiencyScore,
    SourceCoverage,
    CategoryScore,
    DataCategory,
    CoverageGap,
    CoverageReport,
    CRITICAL_SOURCES,
    OPTIONAL_SOURCES,
    calculate_coverage_score,
)
from ..external_apis.openfda_client import OpenFDAClient
from ..external_apis.clinicaltrials_client import ClinicalTrialsClient
from ..external_apis.pubmed_client import PubMedClient
from ..external_apis.patent_client import PatentsViewClient


@dataclass
class SourceCheckResult:
    """Result of checking a data source."""
    source_name: str
    is_available: bool
    record_count: int
    completeness: float
    last_updated: Optional[datetime] = None
    error: Optional[str] = None


class CoverageService:
    """
    Service for calculating data coverage and sufficiency scores.

    Checks multiple data sources to determine how complete the data is
    for a given molecule.
    """

    def __init__(
        self,
        openfda_client: Optional[OpenFDAClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        pubmed_client: Optional[PubMedClient] = None,
        patents_client: Optional[PatentsViewClient] = None,
    ):
        self._openfda = openfda_client or OpenFDAClient()
        self._clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self._pubmed = pubmed_client or PubMedClient()
        self._patents = patents_client or PatentsViewClient()

    async def calculate_coverage(
        self,
        drug_id: str,
        drug_name: str,
        check_all_sources: bool = True,
    ) -> DataSufficiencyScore:
        """
        Calculate data sufficiency score for a molecule.

        Args:
            drug_id: Unique identifier for the drug
            drug_name: Name of the drug for lookups
            check_all_sources: If True, check all sources; if False, check critical only

        Returns:
            DataSufficiencyScore with coverage details
        """
        logger.info(f"Calculating coverage for {drug_name}")

        source_coverage: Dict[str, SourceCoverage] = {}
        missing_critical: List[str] = []
        missing_optional: List[str] = []

        # Check critical sources
        critical_results = await self._check_critical_sources(drug_name)
        for source_name, result in critical_results.items():
            category = CRITICAL_SOURCES.get(source_name, DataCategory.REGULATORY)
            coverage = SourceCoverage(
                source_name=source_name,
                category=category,
                is_available=result.is_available,
                completeness=result.completeness,
                record_count=result.record_count,
                last_updated=result.last_updated,
                critical=True,
            )
            source_coverage[source_name] = coverage

            if not result.is_available:
                missing_critical.append(source_name)

        # Check optional sources if requested
        if check_all_sources:
            optional_results = await self._check_optional_sources(drug_name)
            for source_name, result in optional_results.items():
                category = OPTIONAL_SOURCES.get(source_name, DataCategory.PUBLICATIONS)
                coverage = SourceCoverage(
                    source_name=source_name,
                    category=category,
                    is_available=result.is_available,
                    completeness=result.completeness,
                    record_count=result.record_count,
                    last_updated=result.last_updated,
                    critical=False,
                )
                source_coverage[source_name] = coverage

                if not result.is_available:
                    missing_optional.append(source_name)

        # Calculate category scores
        category_scores = self._calculate_category_scores(source_coverage)

        # Calculate overall score
        overall_score = calculate_coverage_score(source_coverage)
        overall_status = DataSufficiencyScore.calculate_status(overall_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            source_coverage, missing_critical, missing_optional
        )

        return DataSufficiencyScore(
            drug_id=drug_id,
            drug_name=drug_name,
            overall_score=overall_score,
            overall_status=overall_status,
            category_scores=category_scores,
            source_coverage=source_coverage,
            missing_critical=missing_critical,
            missing_optional=missing_optional,
            recommendations=recommendations,
        )

    async def _check_critical_sources(
        self, drug_name: str
    ) -> Dict[str, SourceCheckResult]:
        """Check critical data sources."""
        results: Dict[str, SourceCheckResult] = {}

        # Check FDA approvals (OpenFDA)
        try:
            fda_result = await self._openfda.get_drug_label(drug_name)
            results["fda_approvals"] = SourceCheckResult(
                source_name="fda_approvals",
                is_available=fda_result.success and fda_result.data is not None,
                record_count=1 if fda_result.success else 0,
                completeness=1.0 if fda_result.success else 0.0,
                last_updated=datetime.utcnow() if fda_result.success else None,
            )
        except Exception as e:
            logger.error(f"FDA check failed: {e}")
            results["fda_approvals"] = SourceCheckResult(
                source_name="fda_approvals",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        # Check ClinicalTrials.gov
        try:
            trials_result = await self._clinicaltrials.search_trials(
                intervention=drug_name, limit=100
            )
            trial_count = len(trials_result.data.get("trials", [])) if trials_result.success else 0
            results["clinicaltrials_gov"] = SourceCheckResult(
                source_name="clinicaltrials_gov",
                is_available=trial_count > 0,
                record_count=trial_count,
                completeness=min(1.0, trial_count / 10),  # Scale to 10 trials
                last_updated=datetime.utcnow() if trial_count > 0 else None,
            )
        except Exception as e:
            logger.error(f"ClinicalTrials check failed: {e}")
            results["clinicaltrials_gov"] = SourceCheckResult(
                source_name="clinicaltrials_gov",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        # Check FAERS (OpenFDA adverse events)
        try:
            faers_result = await self._openfda.search_adverse_events(
                drug_name=drug_name, limit=100
            )
            event_count = faers_result.data.get("total", 0) if faers_result.success else 0
            results["faers"] = SourceCheckResult(
                source_name="faers",
                is_available=event_count > 0,
                record_count=event_count,
                completeness=min(1.0, event_count / 100),  # Scale to 100 events
                last_updated=datetime.utcnow() if event_count > 0 else None,
            )
        except Exception as e:
            logger.error(f"FAERS check failed: {e}")
            results["faers"] = SourceCheckResult(
                source_name="faers",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        # Check Orange Book (patents) - using PatentsView as proxy
        try:
            patent_result = await self._patents.search_by_drug(drug_name)
            patent_count = len(patent_result.data.get("patents", [])) if patent_result.success else 0
            results["orange_book"] = SourceCheckResult(
                source_name="orange_book",
                is_available=patent_count > 0,
                record_count=patent_count,
                completeness=min(1.0, patent_count / 5),  # Scale to 5 patents
                last_updated=datetime.utcnow() if patent_count > 0 else None,
            )
        except Exception as e:
            logger.error(f"Orange Book check failed: {e}")
            results["orange_book"] = SourceCheckResult(
                source_name="orange_book",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        return results

    async def _check_optional_sources(
        self, drug_name: str
    ) -> Dict[str, SourceCheckResult]:
        """Check optional data sources."""
        results: Dict[str, SourceCheckResult] = {}

        # Check PubMed publications
        try:
            pubmed_result = await self._pubmed.search(
                query=f'"{drug_name}"[Title/Abstract]',
                max_results=50,
            )
            pub_count = pubmed_result.data.get("total_count", 0) if pubmed_result.success else 0
            results["pubmed"] = SourceCheckResult(
                source_name="pubmed",
                is_available=pub_count > 0,
                record_count=pub_count,
                completeness=min(1.0, pub_count / 20),  # Scale to 20 publications
                last_updated=datetime.utcnow() if pub_count > 0 else None,
            )
        except Exception as e:
            logger.error(f"PubMed check failed: {e}")
            results["pubmed"] = SourceCheckResult(
                source_name="pubmed",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        # Check PatentsView
        try:
            patents_result = await self._patents.search_by_drug(drug_name)
            patent_count = len(patents_result.data.get("patents", [])) if patents_result.success else 0
            results["patents_view"] = SourceCheckResult(
                source_name="patents_view",
                is_available=patent_count > 0,
                record_count=patent_count,
                completeness=min(1.0, patent_count / 10),  # Scale to 10 patents
                last_updated=datetime.utcnow() if patent_count > 0 else None,
            )
        except Exception as e:
            logger.error(f"PatentsView check failed: {e}")
            results["patents_view"] = SourceCheckResult(
                source_name="patents_view",
                is_available=False,
                record_count=0,
                completeness=0.0,
                error=str(e),
            )

        # EMA and Health Canada would be added here when clients are available

        return results

    def _calculate_category_scores(
        self, source_coverage: Dict[str, SourceCoverage]
    ) -> Dict[DataCategory, CategoryScore]:
        """Calculate scores for each data category."""
        category_scores: Dict[DataCategory, CategoryScore] = {}

        # Group sources by category
        by_category: Dict[DataCategory, List[SourceCoverage]] = {}
        for source in source_coverage.values():
            if source.category not in by_category:
                by_category[source.category] = []
            by_category[source.category].append(source)

        # Calculate score for each category
        for category, sources in by_category.items():
            available = sum(1 for s in sources if s.is_available)
            total = len(sources)
            avg_completeness = (
                sum(s.completeness for s in sources) / total if total > 0 else 0.0
            )

            critical_missing = [
                s.source_name for s in sources if s.critical and not s.is_available
            ]

            category_scores[category] = CategoryScore(
                category=category,
                score=avg_completeness * 100,
                sources_available=available,
                sources_total=total,
                critical_sources_missing=critical_missing,
            )

        return category_scores

    def _generate_recommendations(
        self,
        source_coverage: Dict[str, SourceCoverage],
        missing_critical: List[str],
        missing_optional: List[str],
    ) -> List[str]:
        """Generate recommendations based on coverage gaps."""
        recommendations: List[str] = []

        # Critical source recommendations
        if "fda_approvals" in missing_critical:
            recommendations.append(
                "No FDA approval data found. If this drug is approved, verify the drug name spelling."
            )

        if "clinicaltrials_gov" in missing_critical:
            recommendations.append(
                "No clinical trials found. Consider searching with alternative names or synonyms."
            )

        if "faers" in missing_critical:
            recommendations.append(
                "No adverse event data available. This may indicate a pre-approval drug."
            )

        if "orange_book" in missing_critical:
            recommendations.append(
                "No patent data found. Patent exclusivity information may be incomplete."
            )

        # General recommendations based on coverage
        total_completeness = sum(
            s.completeness for s in source_coverage.values()
        ) / max(len(source_coverage), 1)

        if total_completeness < 0.3:
            recommendations.append(
                "Overall data coverage is low. Consider supplementing with manual data entry."
            )
        elif total_completeness < 0.6:
            recommendations.append(
                "Data coverage is moderate. Some competitive intelligence analysis may be limited."
            )

        return recommendations

    async def generate_coverage_report(
        self,
        drug_id: str,
        drug_name: str,
    ) -> CoverageReport:
        """
        Generate a full coverage report with gaps and recommendations.

        Args:
            drug_id: Unique identifier for the drug
            drug_name: Name of the drug

        Returns:
            CoverageReport with full analysis
        """
        # Get sufficiency score
        sufficiency_score = await self.calculate_coverage(drug_id, drug_name)

        # Identify gaps
        gaps = self._identify_gaps(sufficiency_score)

        # Get data freshness
        data_freshness: Dict[str, datetime] = {}
        for source_name, coverage in sufficiency_score.source_coverage.items():
            if coverage.last_updated:
                data_freshness[source_name] = coverage.last_updated

        return CoverageReport(
            drug_id=drug_id,
            drug_name=drug_name,
            sufficiency_score=sufficiency_score,
            gaps=gaps,
            data_freshness=data_freshness,
        )

    def _identify_gaps(
        self, score: DataSufficiencyScore
    ) -> List[CoverageGap]:
        """Identify specific data coverage gaps."""
        gaps: List[CoverageGap] = []

        for source_name, coverage in score.source_coverage.items():
            if not coverage.is_available or coverage.completeness < 0.5:
                severity = "critical" if coverage.critical else "medium"
                if coverage.completeness < 0.2:
                    severity = "critical" if coverage.critical else "high"

                gap = CoverageGap(
                    source=source_name,
                    category=coverage.category,
                    severity=severity,
                    description=f"Data from {source_name} is {'missing' if not coverage.is_available else 'incomplete'}",
                    remediation=self._get_remediation(source_name),
                    estimated_effort="1-2 hours" if coverage.critical else "30 minutes",
                )
                gaps.append(gap)

        return sorted(gaps, key=lambda g: (
            0 if g.severity == "critical" else 1 if g.severity == "high" else 2
        ))

    def _get_remediation(self, source_name: str) -> str:
        """Get remediation suggestion for a missing source."""
        remediations = {
            "fda_approvals": "Verify drug name and check FDA Orange Book manually",
            "clinicaltrials_gov": "Search ClinicalTrials.gov with alternative names",
            "faers": "Drug may be pre-approval; monitor for future safety data",
            "orange_book": "Check FDA Orange Book website directly",
            "pubmed": "Search PubMed with broader search terms",
            "patents_view": "Search USPTO patent database directly",
        }
        return remediations.get(source_name, "Manual data collection may be required")
