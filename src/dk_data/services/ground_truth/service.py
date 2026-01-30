"""
Ground Truth Service - Main Facade.

Provides a unified API for competitive intelligence:
- Build N+2 competitive landscape graphs
- Score competitive threats
- Resolve indications to ICD-10
- Aggregate data from multiple sources
- Generate AI insights

This is the primary entry point for the Ground Truth Service.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from ...models.competitive_graph import (
    CompetitiveLandscapeGraph,
    CompetitiveNode,
    DevelopmentStage,
    ThreatAssessment,
)
from ...models.indication import Indication
from ...models.lifecycle import DataCoverage, DrugLifecycle

from .graph_builder import GraphBuilder, GraphBuilderConfig, get_graph_builder
from .scoring_engine import ScoringEngine, ScoringConfig, get_scoring_engine
from .indication_resolver import IndicationResolver, ResolverConfig, get_indication_resolver, ResolutionResult
from .data_aggregator import DataAggregator, AggregatorConfig, AggregatedDrugData, get_data_aggregator


@dataclass
class GroundTruthConfig:
    """Configuration for the Ground Truth Service."""

    # Component configs
    graph_config: Optional[GraphBuilderConfig] = None
    scoring_config: Optional[ScoringConfig] = None
    resolver_config: Optional[ResolverConfig] = None
    aggregator_config: Optional[AggregatorConfig] = None

    # Service settings
    enable_caching: bool = True
    enable_ai_insights: bool = False  # Requires LLM setup
    default_therapeutic_area: Optional[str] = None


@dataclass
class CompetitiveLandscapeResult:
    """Complete result from competitive landscape analysis."""

    # Core molecule info
    molecule_name: str
    molecule_id: str

    # Graph
    graph: CompetitiveLandscapeGraph

    # Threat assessments
    assessments: List[ThreatAssessment]

    # Summary stats
    total_competitors: int
    critical_threats: int
    high_threats: int

    # Data coverage
    data_coverage: Optional[DataCoverage] = None

    # Auto-fetched input data (for UI display)
    input_data: Optional[Dict[str, Any]] = None

    # Build metadata
    built_at: datetime = field(default_factory=datetime.utcnow)
    build_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "molecule_name": self.molecule_name,
            "molecule_id": self.molecule_id,
            "graph": self.graph.to_dict(),
            "assessments": [a.to_dict() for a in self.assessments],
            "total_competitors": self.total_competitors,
            "critical_threats": self.critical_threats,
            "high_threats": self.high_threats,
            "data_coverage": self.data_coverage.to_dict() if self.data_coverage else None,
            "input_data": self.input_data,
            "built_at": self.built_at.isoformat(),
            "build_time_ms": self.build_time_ms,
        }

    def get_top_threats(self, n: int = 5) -> List[ThreatAssessment]:
        """Get top N threats by score."""
        return self.assessments[:n]

    def get_critical_competitors(self) -> List[CompetitiveNode]:
        """Get competitors with critical threat level."""
        critical_ids = {a.competitor_id for a in self.assessments if a.threat_level == "critical"}
        return [n for n in self.graph.nodes.values() if n.id in critical_ids]


class GroundTruthService:
    """
    Main Ground Truth Service facade.

    Provides a unified interface for all competitive intelligence operations.

    Usage:
        service = GroundTruthService()
        await service.initialize()

        # Build competitive landscape
        result = await service.analyze_competitive_landscape(
            molecule_name="Aspirin",
            molecule_id="DB00945",
            indications=["Rheumatoid Arthritis"],
        )

        # Get top threats
        threats = result.get_top_threats(5)
    """

    def __init__(self, config: Optional[GroundTruthConfig] = None):
        self.config = config or GroundTruthConfig()
        self._graph_builder: Optional[GraphBuilder] = None
        self._scoring_engine: Optional[ScoringEngine] = None
        self._indication_resolver: Optional[IndicationResolver] = None
        self._data_aggregator: Optional[DataAggregator] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all service components."""
        if self._initialized:
            return

        logger.info("Initializing Ground Truth Service...")

        # Initialize components in parallel
        self._graph_builder = await get_graph_builder(self.config.graph_config)
        self._scoring_engine = await get_scoring_engine(self.config.scoring_config)
        self._indication_resolver = await get_indication_resolver(self.config.resolver_config)
        self._data_aggregator = await get_data_aggregator(self.config.aggregator_config)

        self._initialized = True
        logger.info("Ground Truth Service initialized")

    async def analyze_competitive_landscape(
        self,
        molecule_name: str,
        molecule_id: str,
        indications: Optional[List[str]] = None,
        moa: Optional[str] = None,
        targets: Optional[List[str]] = None,
        atc_codes: Optional[List[str]] = None,
        development_stage: Optional[DevelopmentStage] = None,
        sponsor: Optional[str] = None,
        therapeutic_area: Optional[str] = None,
        include_data_coverage: bool = True,
    ) -> CompetitiveLandscapeResult:
        """
        Build and analyze a complete competitive landscape.

        This is the main entry point for competitive intelligence analysis.

        Args:
            molecule_name: Name of the molecule to analyze
            molecule_id: Unique identifier for the molecule
            indications: List of indications (text or ICD-10 codes)
            moa: Mechanism of action
            targets: List of molecular targets
            atc_codes: ATC classification codes
            development_stage: Current development stage
            sponsor: Sponsor/company name
            therapeutic_area: Therapeutic area for weight overrides
            include_data_coverage: Include data coverage analysis

        Returns:
            CompetitiveLandscapeResult with graph, assessments, and stats
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        # AUTO-FETCH drug attributes from FDA label if not provided
        if not indications or not moa:
            logger.info(f"Auto-fetching drug attributes for {molecule_name} from FDA labels")
            fetched_indications, fetched_moa, fetched_therapeutic_area = await self._fetch_drug_attributes(
                molecule_name
            )

            if not indications and fetched_indications:
                indications = fetched_indications
                logger.info(f"Auto-populated {len(indications)} indications for {molecule_name}")

            if not moa and fetched_moa:
                moa = fetched_moa
                logger.info(f"Auto-populated MOA for {molecule_name}: {moa}")

            if not therapeutic_area and fetched_therapeutic_area:
                therapeutic_area = fetched_therapeutic_area
                logger.info(f"Auto-populated therapeutic area for {molecule_name}: {therapeutic_area}")

        # Resolve text indications to ICD-10 if needed
        resolved_indications = []
        if indications:
            for indication in indications:
                if self._is_icd10_code(indication):
                    resolved_indications.append(indication)
                else:
                    result = await self._indication_resolver.resolve(
                        indication,
                        therapeutic_area=therapeutic_area or self.config.default_therapeutic_area,
                    )
                    if result.icd10_code:
                        resolved_indications.append(result.icd10_code)
                    else:
                        # Use original text as fallback
                        resolved_indications.append(indication)

        # Build the competitive graph
        graph = await self._graph_builder.build_graph(
            core_molecule_id=molecule_id,
            core_molecule_name=molecule_name,
            indications=resolved_indications or None,
            moa=moa,
            targets=targets,
            atc_codes=atc_codes,
            development_stage=development_stage,
            sponsor=sponsor,
        )

        # Score all competitors
        assessments = self._scoring_engine.score_graph(
            graph,
            therapeutic_area=therapeutic_area or self.config.default_therapeutic_area,
        )

        # Calculate stats
        critical_count = sum(1 for a in assessments if a.threat_level == "critical")
        high_count = sum(1 for a in assessments if a.threat_level == "high")

        # Get data coverage if requested
        data_coverage = None
        if include_data_coverage:
            aggregated = await self._data_aggregator.aggregate(molecule_name)
            data_coverage = aggregated.coverage

        # Calculate build time
        build_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        # Build input_data summary for UI display
        input_data = {
            "indications": indications or [],
            "resolved_indications": resolved_indications or [],
            "moa": moa,
            "targets": targets or [],
            "atc_codes": atc_codes or [],
            "therapeutic_area": therapeutic_area,
            "development_stage": development_stage.value if development_stage else None,
            "sponsor": sponsor,
        }

        return CompetitiveLandscapeResult(
            molecule_name=molecule_name,
            molecule_id=molecule_id,
            graph=graph,
            assessments=assessments,
            total_competitors=len(assessments),
            critical_threats=critical_count,
            high_threats=high_count,
            data_coverage=data_coverage,
            input_data=input_data,
            built_at=start_time,
            build_time_ms=build_time_ms,
        )

    async def resolve_indication(
        self,
        indication_text: str,
        therapeutic_area: Optional[str] = None,
    ) -> ResolutionResult:
        """
        Resolve a free-text indication to ICD-10 code.

        Args:
            indication_text: Free-text indication
            therapeutic_area: Optional therapeutic area hint

        Returns:
            ResolutionResult with ICD-10 code and confidence
        """
        if not self._initialized:
            await self.initialize()

        return await self._indication_resolver.resolve(
            indication_text,
            therapeutic_area=therapeutic_area or self.config.default_therapeutic_area,
        )

    async def aggregate_drug_data(
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
        if not self._initialized:
            await self.initialize()

        return await self._data_aggregator.aggregate(
            drug_name,
            include_trials=include_trials,
            include_safety=include_safety,
        )

    async def get_competitors_for_indication(
        self,
        indication: str,
        therapeutic_area: Optional[str] = None,
        min_phase: str = "PHASE2",
    ) -> List[Dict[str, Any]]:
        """
        Find all competitors for a given indication.

        Args:
            indication: Indication text or ICD-10 code
            therapeutic_area: Therapeutic area hint
            min_phase: Minimum development phase

        Returns:
            List of competitor info dicts
        """
        if not self._initialized:
            await self.initialize()

        # Resolve indication if needed
        if not self._is_icd10_code(indication):
            result = await self._indication_resolver.resolve(indication, therapeutic_area)
            if result.icd10_code:
                indication = result.icd10_code

        # Get competitors from clinical trials
        from ..external_apis import get_clinicaltrials_client
        ct_client = await get_clinicaltrials_client()

        competitors = await ct_client.get_competitors_for_indication(
            indication=indication,
            phases=[min_phase, "PHASE3"],
        )

        # Format results
        results = []
        for drug_name, trials in competitors.items():
            results.append({
                "drug_name": drug_name,
                "trial_count": len(trials),
                "phases": list(set(t.phase.value for t in trials)),
                "sponsors": list(set(t.lead_sponsor.name for t in trials if t.lead_sponsor)),
                "indication": indication,
            })

        # Sort by trial count
        results.sort(key=lambda x: x["trial_count"], reverse=True)

        return results

    async def assess_single_competitor(
        self,
        core_molecule_name: str,
        core_molecule_id: str,
        competitor_name: str,
        competitor_id: str,
        shared_indications: Optional[List[str]] = None,
        shared_moa: bool = False,
        competitor_stage: DevelopmentStage = DevelopmentStage.PHASE_2,
        therapeutic_area: Optional[str] = None,
    ) -> ThreatAssessment:
        """
        Assess threat from a single competitor.

        Args:
            core_molecule_name: Name of core molecule
            core_molecule_id: ID of core molecule
            competitor_name: Name of competitor
            competitor_id: ID of competitor
            shared_indications: List of shared indications
            shared_moa: Whether they share MOA
            competitor_stage: Development stage of competitor
            therapeutic_area: Therapeutic area for weights

        Returns:
            ThreatAssessment for the competitor
        """
        if not self._initialized:
            await self.initialize()

        from ...models.competitive_graph import (
            CompetitiveDimension,
            CompetitiveEdge,
            GraphLevel,
        )

        # Create minimal nodes
        core_node = CompetitiveNode(
            id=core_molecule_id,
            name=core_molecule_name,
            level=GraphLevel.CORE,
        )

        competitor_node = CompetitiveNode(
            id=competitor_id,
            name=competitor_name,
            level=GraphLevel.N_PLUS_1,
            development_stage=competitor_stage,
        )

        # Create edges based on shared attributes
        edges = []

        if shared_indications:
            edges.append(CompetitiveEdge(
                source_id=core_molecule_id,
                target_id=competitor_id,
                dimension=CompetitiveDimension.INDICATION,
                score=min(1.0, len(shared_indications) * 0.3),
                evidence=[f"Shared indication: {i}" for i in shared_indications],
            ))

        if shared_moa:
            edges.append(CompetitiveEdge(
                source_id=core_molecule_id,
                target_id=competitor_id,
                dimension=CompetitiveDimension.MOA,
                score=1.0,
                evidence=["Same mechanism of action"],
            ))

        # Score the competitor
        return self._scoring_engine.assess_threat(
            core_node=core_node,
            competitor_node=competitor_node,
            edges=edges,
            therapeutic_area=therapeutic_area or self.config.default_therapeutic_area,
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all service components.

        Returns:
            Health status for each component
        """
        from ..external_apis import (
            get_umls_client,
            get_rxnorm_client,
            get_openfda_client,
            get_clinicaltrials_client,
            get_ema_client,
        )

        status = {
            "service": "ground_truth",
            "initialized": self._initialized,
            "components": {},
            "sources": [],
        }

        # Check database tables (local sources)
        from .db_utils import get_db_connection
        
        async def check_table_exists(table_name: str) -> bool:
            try:
                async with get_db_connection() as conn:
                    result = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = $1
                        )
                    """, table_name)
                    return result or False
            except Exception:
                return False
        
        async def get_table_count(table_name: str) -> int:
            try:
                async with get_db_connection() as conn:
                    result = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                    return result or 0
            except Exception:
                return 0

        # Local database sources
        local_sources = [
            ("pharma_predictor_db", "pharma_predictor_db", "Local database"),
            ("Clinical Trials (Local)", "clinical_trials", "Clinical trials database"),
            ("FDA Labels (Local)", "fda_labels", "FDA drug labels and approvals"),
            ("Regulatory Milestones", "regulatory_milestones", "Regulatory approval history"),
            ("Patents (Local)", "patents", "Patent information database"),
            ("Publications (Local)", "publications", "Scientific publications database"),
            ("ChEMBL", "chembl_compounds", "Bioactivity data, targets, activities"),
            ("DrugBank", "drugbank_data", "Drug interactions, pharmacology, pathways"),
            ("SIDER", "sider_adverse_reactions", "Side effects and adverse reactions"),
            ("BindingDB", "bindingdb_affinities", "Binding affinities and target data"),
            ("WHO INN", "who_inn_names", "International Nonproprietary Names"),
            ("FAERS", "faers_adverse_events", "FDA Adverse Event Reporting System"),
        ]
        
        for source_name, table_name, description in local_sources:
            try:
                exists = await check_table_exists(table_name)
                record_count = await get_table_count(table_name) if exists else 0
                status["sources"].append({
                    "name": source_name,
                    "available": exists,
                    "record_count": record_count,
                    "category": "local",
                    "description": description,
                })
            except Exception as e:
                logger.debug(f"Failed to check {source_name}: {e}")
                status["sources"].append({
                    "name": source_name,
                    "available": False,
                    "record_count": 0,
                    "category": "local",
                    "description": description,
                })

        # Check external APIs
        external_sources = [
            ("PubChem", None, "Molecular properties, identifiers", True),
            ("OpenFDA", get_openfda_client, "Drug labels, adverse events, recalls", None),
            ("ClinicalTrials.gov", get_clinicaltrials_client, "Clinical trial data (external API)", None),
            ("RxNorm", get_rxnorm_client, "Drug nomenclature (external API)", None),
            ("OpenAlex", None, "Scientific publications (external API)", True),
            ("PatentsView", None, "USPTO patent data (API key required)", True),
        ]
        
        # Try to add EMA if available
        try:
            from ..external_apis.ema_client import EMAClient
            ema_client = EMAClient()
            external_sources.append(("EMA Medicines", lambda: ema_client, "European authorized medicines", None))
        except ImportError:
            pass
        
        for source_info in external_sources:
            source_name = source_info[0]
            client_getter = source_info[1]
            description = source_info[2]
            always_available = source_info[3] if len(source_info) > 3 else None
            
            try:
                if always_available is True:
                    # These are always available (no health check needed)
                    available = True
                elif client_getter is None:
                    available = True
                else:
                    try:
                        client = await client_getter() if callable(client_getter) else client_getter
                        available = await client.health_check() if hasattr(client, 'health_check') else True
                    except Exception as e:
                        logger.debug(f"{source_name} client creation failed: {e}")
                        available = False
                
                status["components"][source_name.lower().replace(" ", "_").replace(".", "")] = available
                status["sources"].append({
                    "name": source_name,
                    "available": available,
                    "record_count": 0,  # External APIs don't provide counts easily
                    "category": "external",
                    "description": description,
                })
            except Exception as e:
                logger.debug(f"{source_name} health check failed: {e}")
                status["components"][source_name.lower().replace(" ", "_").replace(".", "")] = False
                status["sources"].append({
                    "name": source_name,
                    "available": False,
                    "record_count": 0,
                    "category": "external",
                    "description": description,
                })

        # Overall status
        status["healthy"] = all(status["components"].values()) if status["components"] else True

        return status

    async def _fetch_drug_attributes(
        self,
        drug_name: str,
    ) -> tuple[List[str], Optional[str], Optional[str]]:
        """
        Fetch drug attributes (indications, MOA, therapeutic area) from FDA label data.

        Args:
            drug_name: Name of the drug to look up

        Returns:
            Tuple of (indications, moa, therapeutic_area)
        """
        from ..external_apis import get_openfda_client

        indications: List[str] = []
        moa: Optional[str] = None
        therapeutic_area: Optional[str] = None

        try:
            openfda = await get_openfda_client()

            # Search for drug labels
            labels = await openfda.search_drug_labels(drug_name, limit=5)

            if not labels:
                # Try brand name search
                labels = await openfda.search_drug_labels(
                    drug_name,
                    search_field="openfda.brand_name",
                    limit=5
                )

            if labels:
                label = labels[0]  # Use first (most relevant) label

                # Extract MOA from pharmacological class
                if label.pharm_class_moa:
                    moa = label.pharm_class_moa[0]
                elif label.mechanism_of_action:
                    # Extract key phrase from full MOA text
                    moa = self._extract_moa_keyword(label.mechanism_of_action)

                # Extract therapeutic area from established pharmacological class
                if label.pharm_class_epc:
                    therapeutic_area = self._map_pharm_class_to_therapeutic_area(
                        label.pharm_class_epc[0]
                    )

                # Extract indications from label text
                if label.indications_and_usage:
                    indications = self._extract_indication_keywords(
                        label.indications_and_usage
                    )

                logger.info(
                    f"Fetched FDA label for {drug_name}: "
                    f"{len(indications)} indications, MOA={moa}, TA={therapeutic_area}"
                )

        except Exception as e:
            logger.warning(f"Could not fetch FDA attributes for {drug_name}: {e}")

        return indications, moa, therapeutic_area

    def _extract_moa_keyword(self, moa_text: str) -> Optional[str]:
        """Extract a searchable MOA keyword from full MOA text."""
        if not moa_text:
            return None

        # Common MOA patterns to extract
        import re

        # Look for "X inhibitor", "X antagonist", "X agonist", "X blocker" patterns
        patterns = [
            r'(\w+(?:\s+\w+)?\s+(?:inhibitor|antagonist|agonist|blocker|activator|modulator))',
            r'(anti-\w+)',
            r'(monoclonal antibody(?:\s+(?:targeting|against|to)\s+\w+)?)',
        ]

        moa_lower = moa_text.lower()
        for pattern in patterns:
            match = re.search(pattern, moa_lower, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: return first 50 chars
        return moa_text[:50] if len(moa_text) > 50 else moa_text

    def _extract_indication_keywords(self, indication_texts: List[str]) -> List[str]:
        """Extract searchable disease/condition keywords from indication text."""
        import re

        # Common disease patterns to extract
        disease_patterns = [
            # Specific disease names
            r'(atopic dermatitis)',
            r'(asthma)',
            r'(chronic rhinosinusitis with nasal polyps|nasal polyps)',
            r'(eosinophilic esophagitis)',
            r'(prurigo nodularis)',
            r'(chronic spontaneous urticaria)',
            r'(rheumatoid arthritis)',
            r'(psoriasis|plaque psoriasis|psoriatic arthritis)',
            r'(crohn\'?s? disease)',
            r'(ulcerative colitis)',
            r'(multiple sclerosis)',
            r'(non-small cell lung cancer|nsclc)',
            r'(breast cancer)',
            r'(melanoma)',
            r'(lymphoma)',
            r'(leukemia)',
            r'(diabetes|type \d diabetes)',
            r'(hypertension)',
            r'(heart failure)',
            r'(copd|chronic obstructive pulmonary disease)',
            r'(alzheimer\'?s? disease)',
            r'(parkinson\'?s? disease)',
            r'(epilepsy)',
            r'(depression|major depressive disorder)',
            r'(schizophrenia)',
            r'(anxiety|generalized anxiety disorder)',
            r'(hiv|human immunodeficiency virus)',
            r'(hepatitis [abc])',
            r'(covid-19|sars-cov-2)',
            r'(influenza)',
            # Generic patterns
            r'((?:moderate[- ]to[- ]severe|severe|chronic|acute)\s+\w+(?:\s+\w+)?)',
        ]

        indications = set()
        full_text = " ".join(indication_texts).lower()

        for pattern in disease_patterns:
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                cleaned = match.strip().title()
                if len(cleaned) > 3:  # Skip very short matches
                    indications.add(cleaned)

        # Limit to top indications to avoid too broad searches
        return list(indications)[:10]

    def _map_pharm_class_to_therapeutic_area(self, pharm_class: str) -> Optional[str]:
        """Map FDA pharmacological class to therapeutic area."""
        pharm_lower = pharm_class.lower()

        mappings = {
            "immunology": ["interleukin", "immunomodulator", "immunosuppressant", "anti-inflammatory", "tnf", "jak"],
            "oncology": ["antineoplastic", "kinase inhibitor", "checkpoint inhibitor", "anti-cancer", "cytotoxic"],
            "cardiology": ["antihypertensive", "cardiovascular", "anticoagulant", "antiarrhythmic", "heart"],
            "neurology": ["antiepileptic", "antipsychotic", "antidepressant", "anxiolytic", "dopamine", "serotonin"],
            "infectious disease": ["antibiotic", "antiviral", "antifungal", "antimicrobial", "hiv", "hepatitis"],
            "respiratory": ["bronchodilator", "respiratory", "asthma", "copd", "pulmonary"],
            "endocrinology": ["antidiabetic", "insulin", "thyroid", "hormone", "glucagon"],
            "rheumatology": ["antirheumatic", "disease-modifying", "dmard", "arthritis"],
            "dermatology": ["dermatologic", "skin", "psoriasis", "eczema", "dermatitis"],
            "gastroenterology": ["gastrointestinal", "proton pump", "antacid", "gi", "bowel"],
        }

        for ta, keywords in mappings.items():
            if any(kw in pharm_lower for kw in keywords):
                return ta.title()

        return None

    def _is_icd10_code(self, text: str) -> bool:
        """Check if text looks like an ICD-10 code."""
        import re
        # ICD-10 codes start with a letter, followed by digits and optional decimal
        pattern = r'^[A-Z]\d{2}(\.\d{1,4})?$'
        return bool(re.match(pattern, text.upper()))


# =============================================================================
# Analysis Cache for Recent Analyses
# =============================================================================

@dataclass
class CachedAnalysis:
    """Cached competitive landscape analysis summary."""
    id: str
    molecule_name: str
    molecule_id: str
    indication: Optional[str]
    competitor_count: int
    critical_threats: int
    high_threats: int
    timestamp: str
    build_time_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "molecule_name": self.molecule_name,
            "molecule_id": self.molecule_id,
            "indication": self.indication,
            "competitor_count": self.competitor_count,
            "critical_threats": self.critical_threats,
            "high_threats": self.high_threats,
            "timestamp": self.timestamp,
            "build_time_ms": self.build_time_ms,
        }


class AnalysisCache:
    """In-memory cache for recent competitive landscape analyses."""

    def __init__(self, max_size: int = 50):
        self._cache: Dict[str, CachedAnalysis] = {}
        self._order: List[str] = []  # Track insertion order
        self._max_size = max_size

    def add(self, result: CompetitiveLandscapeResult) -> CachedAnalysis:
        """Add an analysis result to the cache."""
        import uuid

        cache_id = str(uuid.uuid4())[:8]

        # Get primary indication from input data
        indication = None
        if result.input_data and result.input_data.get("indications"):
            indication = result.input_data["indications"][0]

        cached = CachedAnalysis(
            id=cache_id,
            molecule_name=result.molecule_name,
            molecule_id=result.molecule_id,
            indication=indication,
            competitor_count=result.total_competitors,
            critical_threats=result.critical_threats,
            high_threats=result.high_threats,
            timestamp=result.built_at.isoformat(),
            build_time_ms=result.build_time_ms,
        )

        # Add to cache
        self._cache[cache_id] = cached
        self._order.insert(0, cache_id)

        # Evict oldest if over max size
        while len(self._order) > self._max_size:
            old_id = self._order.pop()
            if old_id in self._cache:
                del self._cache[old_id]

        return cached

    def get_recent(self, limit: int = 10) -> List[CachedAnalysis]:
        """Get most recent analyses."""
        return [self._cache[id] for id in self._order[:limit] if id in self._cache]

    def get_by_id(self, cache_id: str) -> Optional[CachedAnalysis]:
        """Get a specific cached analysis."""
        return self._cache.get(cache_id)

    def clear(self) -> None:
        """Clear all cached analyses."""
        self._cache.clear()
        self._order.clear()


# Global cache instance
_analysis_cache = AnalysisCache()


def get_analysis_cache() -> AnalysisCache:
    """Get the global analysis cache instance."""
    return _analysis_cache


# Singleton instance
_ground_truth_service: Optional[GroundTruthService] = None


async def get_ground_truth_service(config: Optional[GroundTruthConfig] = None) -> GroundTruthService:
    """Get or create the Ground Truth Service instance."""
    global _ground_truth_service

    if _ground_truth_service is None:
        _ground_truth_service = GroundTruthService(config)
        await _ground_truth_service.initialize()

    return _ground_truth_service
