"""
Data Aggregator Service.

Orchestrates data retrieval from multiple external sources:
- Parallel fetching with error handling
- Source priority resolution for conflicts
- Data coverage tracking
- Critical vs non-critical source handling

Supports graceful degradation when non-critical sources fail.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from ...models.lifecycle import (
    DataCoverage,
    DataSourceCategory,
    DataSourceStatus,
)
from ..external_apis import (
    ClinicalTrialsClient,
    ClinicalTrial,
    OpenFDAClient,
    DrugLabel,
    RxNormClient,
    UMLSClient,
    get_clinicaltrials_client,
    get_openfda_client,
    get_rxnorm_client,
    get_umls_client,
    is_critical_source,
)


@dataclass
class AggregatedDrugData:
    """Aggregated data for a drug from all sources."""

    # Input identifier
    drug_name: str
    drug_id: Optional[str] = None

    # Identifiers from various sources
    rxcui: Optional[str] = None
    drugbank_id: Optional[str] = None
    chembl_id: Optional[str] = None
    inchi_key: Optional[str] = None
    ndc_codes: List[str] = field(default_factory=list)

    # Normalized names
    generic_name: Optional[str] = None
    brand_names: List[str] = field(default_factory=list)

    # Clinical data
    indications: List[str] = field(default_factory=list)
    mechanism_of_action: Optional[str] = None
    atc_codes: List[str] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)

    # Regulatory data
    application_numbers: List[str] = field(default_factory=list)  # NDA/BLA
    approval_status: Optional[str] = None
    manufacturer: Optional[str] = None

    # Clinical trials
    active_trials: List[Dict[str, Any]] = field(default_factory=list)
    trial_phases: Dict[str, int] = field(default_factory=dict)  # Phase -> count

    # Safety
    adverse_events_count: int = 0
    boxed_warning: bool = False

    # Source tracking
    sources_queried: List[str] = field(default_factory=list)
    sources_with_data: List[str] = field(default_factory=list)
    source_errors: Dict[str, str] = field(default_factory=dict)
    
    # Internal tracking for coverage calculation
    _openfda_label_count: int = 0

    # Data coverage
    coverage: Optional[DataCoverage] = None

    # Timestamps
    aggregated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drug_name": self.drug_name,
            "drug_id": self.drug_id,
            "rxcui": self.rxcui,
            "drugbank_id": self.drugbank_id,
            "chembl_id": self.chembl_id,
            "inchi_key": self.inchi_key,
            "ndc_codes": self.ndc_codes,
            "generic_name": self.generic_name,
            "brand_names": self.brand_names,
            "indications": self.indications,
            "mechanism_of_action": self.mechanism_of_action,
            "atc_codes": self.atc_codes,
            "targets": self.targets,
            "application_numbers": self.application_numbers,
            "approval_status": self.approval_status,
            "manufacturer": self.manufacturer,
            "active_trials": self.active_trials,
            "trial_phases": self.trial_phases,
            "adverse_events_count": self.adverse_events_count,
            "boxed_warning": self.boxed_warning,
            "sources_queried": self.sources_queried,
            "sources_with_data": self.sources_with_data,
            "source_errors": self.source_errors,
            "coverage": self.coverage.to_dict() if self.coverage else None,
            "aggregated_at": self.aggregated_at.isoformat(),
        }


@dataclass
class AggregatorConfig:
    """Configuration for data aggregation."""

    # Source priority (higher = preferred)
    source_priority: Dict[str, int] = field(default_factory=lambda: {
        "fda_labels": 10,
        "clinicaltrials": 9,
        "rxnorm": 8,
        "drugbank": 7,
        "chembl": 6,
        "pubchem": 5,
        "umls": 4,
    })

    # Timeout per source (seconds)
    source_timeout: float = 30.0

    # Maximum parallel requests
    max_parallel: int = 5

    # Retry failed critical sources
    retry_critical: bool = True
    max_retries: int = 2


class DataAggregator:
    """
    Aggregates drug data from multiple sources.

    Usage:
        aggregator = DataAggregator()
        await aggregator.initialize()

        data = await aggregator.aggregate("aspirin")
        print(data.mechanism_of_action)
    """

    def __init__(self, config: Optional[AggregatorConfig] = None):
        self.config = config or AggregatorConfig()
        self._umls: Optional[UMLSClient] = None
        self._rxnorm: Optional[RxNormClient] = None
        self._openfda: Optional[OpenFDAClient] = None
        self._clinicaltrials: Optional[ClinicalTrialsClient] = None

    async def initialize(self) -> None:
        """Initialize API clients."""
        self._umls = await get_umls_client()
        self._rxnorm = await get_rxnorm_client()
        self._openfda = await get_openfda_client()
        self._clinicaltrials = await get_clinicaltrials_client()

    async def aggregate(
        self,
        drug_name: str,
        include_trials: bool = True,
        include_safety: bool = True,
    ) -> AggregatedDrugData:
        """
        Aggregate data for a drug from all sources.

        Args:
            drug_name: Drug name to search
            include_trials: Include clinical trial data
            include_safety: Include adverse event data

        Returns:
            AggregatedDrugData with combined information
        """
        result = AggregatedDrugData(drug_name=drug_name)

        # Define fetch tasks
        tasks = {
            "rxnorm": self._fetch_rxnorm(drug_name),
            "openfda": self._fetch_openfda(drug_name),
        }

        if include_trials:
            tasks["clinicaltrials"] = self._fetch_trials(drug_name)

        if include_safety:
            tasks["openfda_faers"] = self._fetch_adverse_events(drug_name)

        # Execute tasks with timeout
        results = await self._execute_parallel(tasks)

        # Process RxNorm results
        rxnorm_data = results.get("rxnorm")
        if rxnorm_data and not isinstance(rxnorm_data, Exception):
            result.sources_with_data.append("rxnorm")
            self._merge_rxnorm(result, rxnorm_data)
        elif isinstance(rxnorm_data, Exception):
            result.source_errors["rxnorm"] = str(rxnorm_data)

        # Process OpenFDA results
        openfda_data = results.get("openfda")
        if openfda_data and not isinstance(openfda_data, Exception):
            result.sources_with_data.append("openfda")
            # Store label count for later use in coverage calculation
            result._openfda_label_count = len(openfda_data) if isinstance(openfda_data, list) else 0
            self._merge_openfda(result, openfda_data)
        elif isinstance(openfda_data, Exception):
            result.source_errors["openfda"] = str(openfda_data)
            result._openfda_label_count = 0

        # Process clinical trials
        if include_trials:
            trials_data = results.get("clinicaltrials")
            if trials_data and not isinstance(trials_data, Exception):
                result.sources_with_data.append("clinicaltrials")
                self._merge_trials(result, trials_data)
            elif isinstance(trials_data, Exception):
                result.source_errors["clinicaltrials"] = str(trials_data)

        # Process adverse events
        if include_safety:
            faers_data = results.get("openfda_faers")
            if faers_data and not isinstance(faers_data, Exception):
                result.sources_with_data.append("openfda_faers")
                result.adverse_events_count = faers_data.get("count", 0)
            elif isinstance(faers_data, Exception):
                result.source_errors["openfda_faers"] = str(faers_data)

        # Track sources queried
        result.sources_queried = list(tasks.keys())

        # Calculate data coverage
        result.coverage = self._calculate_coverage(result)

        # Check for critical source failures
        self._check_critical_failures(result)

        return result

    async def _execute_parallel(
        self,
        tasks: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute tasks in parallel with timeout and error handling."""
        results = {}

        # Create async tasks
        async_tasks = []
        task_names = []

        for name, coro in tasks.items():
            task_names.append(name)
            async_tasks.append(
                asyncio.wait_for(coro, timeout=self.config.source_timeout)
            )

        # Execute with gather
        task_results = await asyncio.gather(*async_tasks, return_exceptions=True)

        # Map results
        for name, result in zip(task_names, task_results):
            results[name] = result

        return results

    async def _fetch_rxnorm(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Fetch data from RxNorm."""
        try:
            normalized = await self._rxnorm.normalize_drug_name(drug_name)
            if normalized:
                return normalized
        except Exception as e:
            logger.error(f"RxNorm fetch error for {drug_name}: {e}")
            raise
        return None

    async def _fetch_openfda(self, drug_name: str) -> Optional[List[DrugLabel]]:
        """Fetch data from OpenFDA drug labels."""
        try:
            labels = await self._openfda.search_drug_labels(
                query=drug_name,
                limit=5,
            )
            return labels if labels else None
        except Exception as e:
            logger.error(f"OpenFDA fetch error for {drug_name}: {e}")
            raise

    async def _fetch_trials(self, drug_name: str) -> Optional[List[ClinicalTrial]]:
        """Fetch clinical trials."""
        try:
            trials = await self._clinicaltrials.search_by_drug(
                drug_name=drug_name,
                active_only=True,
                page_size=50,
            )
            return trials if trials else None
        except Exception as e:
            logger.error(f"ClinicalTrials fetch error for {drug_name}: {e}")
            raise

    async def _fetch_adverse_events(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Fetch adverse event counts from FAERS."""
        try:
            counts = await self._openfda.count_adverse_events(drug_name)
            total = sum(counts.values())
            return {"count": total, "by_reaction": counts}
        except Exception as e:
            logger.error(f"FAERS fetch error for {drug_name}: {e}")
            raise

    def _merge_rxnorm(self, result: AggregatedDrugData, data: Dict[str, Any]) -> None:
        """Merge RxNorm data into result."""
        result.rxcui = data.get("rxcui")
        result.generic_name = data.get("normalized_name")
        result.atc_codes = data.get("atc_codes", [])

        ingredients = data.get("ingredients", [])
        if ingredients:
            result.targets = [i.get("name", "") for i in ingredients if i.get("name")]

    def _merge_openfda(self, result: AggregatedDrugData, labels: List[DrugLabel]) -> None:
        """Merge OpenFDA label data into result."""
        if not labels:
            return

        # Use first label as primary
        primary = labels[0]

        if not result.generic_name and primary.generic_name:
            result.generic_name = primary.generic_name

        if primary.brand_name:
            result.brand_names.append(primary.brand_name)

        if primary.mechanism_of_action:
            result.mechanism_of_action = primary.mechanism_of_action
        elif primary.pharm_class_moa:
            result.mechanism_of_action = primary.pharm_class_moa[0]

        if primary.indications_and_usage:
            result.indications.extend(primary.indications_and_usage[:3])

        if primary.application_number:
            result.application_numbers.append(primary.application_number)

        if primary.manufacturer_name:
            result.manufacturer = primary.manufacturer_name

        if primary.boxed_warning:
            result.boxed_warning = True

        result.ndc_codes.extend(primary.product_ndc)
        result.approval_status = "approved"  # If in OpenFDA, it's approved

    def _merge_trials(self, result: AggregatedDrugData, trials: List[ClinicalTrial]) -> None:
        """Merge clinical trial data into result."""
        phase_counts: Dict[str, int] = {}

        for trial in trials[:20]:  # Limit for performance
            phase = trial.phase.value
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

            result.active_trials.append({
                "nct_id": trial.nct_id,
                "title": trial.brief_title,
                "phase": phase,
                "status": trial.overall_status.value,
                "sponsor": trial.lead_sponsor.name if trial.lead_sponsor else None,
                "conditions": trial.conditions[:3],
            })

        result.trial_phases = phase_counts

    def _calculate_coverage(self, result: AggregatedDrugData) -> DataCoverage:
        """Calculate data coverage score."""
        coverage = DataCoverage(
            drug_id=result.drug_id or result.drug_name,
            drug_name=result.drug_name,
        )

        # Identifiers category - count all identifier types found
        identifier_count = sum([
            1 if result.rxcui else 0,
            1 if result.drugbank_id else 0,
            1 if result.chembl_id else 0,
            1 if result.inchi_key else 0,
            len(result.ndc_codes),
        ])
        id_status = DataSourceStatus(
            source_name="identifiers",
            category=DataSourceCategory.IDENTIFIERS,
            is_available=bool(result.rxcui or result.ndc_codes or result.drugbank_id or result.chembl_id or result.inchi_key),
            fetch_attempted=True,
            completeness=self._calculate_id_completeness(result),
            record_count=identifier_count,
        )
        coverage.add_source_status(id_status)

        # Clinical trials category
        trials_status = DataSourceStatus(
            source_name="clinicaltrials",
            category=DataSourceCategory.CLINICAL_TRIALS,
            is_available=bool(result.active_trials),
            fetch_attempted="clinicaltrials" in result.sources_queried,
            completeness=min(1.0, len(result.active_trials) / 10),
            record_count=len(result.active_trials),
        )
        coverage.add_source_status(trials_status)

        # Regulatory category - count OpenFDA labels found
        # Use stored label count if available, otherwise count based on extracted data
        openfda_label_count = getattr(result, '_openfda_label_count', 0)
        if openfda_label_count == 0 and "openfda" in result.sources_with_data:
            # Fallback: count based on data extracted from OpenFDA
            openfda_label_count = sum([
                1 if result.approval_status else 0,
                1 if result.mechanism_of_action else 0,
                1 if result.indications else 0,
                1 if result.application_numbers else 0,
                1 if result.manufacturer else 0,
            ])
        reg_status = DataSourceStatus(
            source_name="openfda",
            category=DataSourceCategory.REGULATORY,
            is_available=result.approval_status is not None or bool(result.mechanism_of_action or result.indications),
            fetch_attempted="openfda" in result.sources_queried,
            completeness=1.0 if (result.approval_status or result.mechanism_of_action or result.indications) else 0.0,
            record_count=openfda_label_count,
        )
        coverage.add_source_status(reg_status)

        # Safety category
        safety_status = DataSourceStatus(
            source_name="openfda_faers",
            category=DataSourceCategory.SAFETY,
            is_available=result.adverse_events_count > 0,
            fetch_attempted="openfda_faers" in result.sources_queried,
            completeness=min(1.0, result.adverse_events_count / 100),
            record_count=result.adverse_events_count,
        )
        coverage.add_source_status(safety_status)

        return coverage

    def _calculate_id_completeness(self, result: AggregatedDrugData) -> float:
        """Calculate identifier completeness score."""
        score = 0.0
        if result.rxcui:
            score += 0.25
        if result.drugbank_id:
            score += 0.25
        if result.ndc_codes:
            score += 0.25
        if result.inchi_key:
            score += 0.25
        return score

    def _check_critical_failures(self, result: AggregatedDrugData) -> None:
        """Check if critical sources failed and raise if needed."""
        critical_failures = []

        for source, error in result.source_errors.items():
            if is_critical_source(source):
                critical_failures.append(f"{source}: {error}")

        if critical_failures:
            logger.warning(f"Critical source failures for {result.drug_name}: {critical_failures}")
            # Don't raise - allow graceful degradation
            # But log for monitoring

    async def aggregate_batch(
        self,
        drug_names: List[str],
        include_trials: bool = True,
        include_safety: bool = False,
    ) -> List[AggregatedDrugData]:
        """
        Aggregate data for multiple drugs.

        Args:
            drug_names: List of drug names
            include_trials: Include clinical trial data
            include_safety: Include adverse event data

        Returns:
            List of AggregatedDrugData
        """
        results = []

        # Process in batches to avoid overwhelming APIs
        batch_size = self.config.max_parallel

        for i in range(0, len(drug_names), batch_size):
            batch = drug_names[i:i + batch_size]
            tasks = [
                self.aggregate(name, include_trials, include_safety)
                for name in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for name, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Aggregation failed for {name}: {result}")
                    # Create minimal result
                    results.append(AggregatedDrugData(
                        drug_name=name,
                        source_errors={"aggregation": str(result)},
                    ))
                else:
                    results.append(result)

        return results


# Singleton instance
_data_aggregator: Optional[DataAggregator] = None


async def get_data_aggregator(config: Optional[AggregatorConfig] = None) -> DataAggregator:
    """Get or create the data aggregator instance."""
    global _data_aggregator

    if _data_aggregator is None:
        _data_aggregator = DataAggregator(config)
        await _data_aggregator.initialize()

    return _data_aggregator
