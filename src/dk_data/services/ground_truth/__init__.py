"""
Ground Truth Service Package.

Provides competitive intelligence capabilities:
- N+2 competitive landscape graphs
- Threat scoring and assessment
- Indication resolution (text to ICD-10)
- Multi-source data aggregation

Main entry point: GroundTruthService
"""

from .service import (
    GroundTruthService,
    GroundTruthConfig,
    CompetitiveLandscapeResult,
    get_ground_truth_service,
    # Analysis cache
    AnalysisCache,
    CachedAnalysis,
    get_analysis_cache,
)

from .graph_builder import (
    GraphBuilder,
    GraphBuilderConfig,
    get_graph_builder,
)

from .scoring_engine import (
    ScoringEngine,
    ScoringConfig,
    ThreatLevel,
    TimeHorizon,
    get_scoring_engine,
)

from .indication_resolver import (
    IndicationResolver,
    ResolverConfig,
    ResolutionResult,
    get_indication_resolver,
)

from .data_aggregator import (
    DataAggregator,
    AggregatorConfig,
    AggregatedDrugData,
    get_data_aggregator,
)

from .clinical_endpoints_loader import (
    ClinicalEndpointsOntology,
    get_clinical_endpoints_ontology,
)

from .ontology_loader import (
    OntologyLoader,
    OntologyMappings,
    get_ontology_loader,
    get_ontology_mappings,
)

from .iva_evidence_report_workflow import (
    IVAEvidenceReportWorkflow,
    generate_iva_evidence_report,
    WorkflowInputs as EvidenceReportInputs,
    WorkflowOutputs as EvidenceReportOutputs,
    CEJNarrativePillar,
    EvidenceStrength,
    GapStatus,
)

from .competitive_graph_service import (
    CompetitiveGraphService,
)

from .coverage_service import (
    CoverageService,
)

from .feedback_service import (
    UserFeedbackService as FeedbackService,
    FeedbackType,
    FeedbackTicket as Feedback,
)

from .kol_service import (
    KOLIntelligenceService as KOLService,
    KOL,
)

from .onboarding_service import (
    UserOnboardingService as OnboardingService,
)

from .visualization_service import (
    VisualizationService,
)

from .lifecycle_service import (
    LifecycleService,
    MilestoneType,
)

from .global_regulatory_service import (
    GlobalRegulatoryService,
    RegulatoryRegion,
    ApprovalStatus,
)

__all__ = [
    # Main service
    "GroundTruthService",
    "GroundTruthConfig",
    "CompetitiveLandscapeResult",
    "get_ground_truth_service",
    # Analysis cache
    "AnalysisCache",
    "CachedAnalysis",
    "get_analysis_cache",
    # Graph builder
    "GraphBuilder",
    "GraphBuilderConfig",
    "get_graph_builder",
    # Scoring engine
    "ScoringEngine",
    "ScoringConfig",
    "ThreatLevel",
    "TimeHorizon",
    "get_scoring_engine",
    # Indication resolver
    "IndicationResolver",
    "ResolverConfig",
    "ResolutionResult",
    "get_indication_resolver",
    # Data aggregator
    "DataAggregator",
    "AggregatorConfig",
    "AggregatedDrugData",
    "get_data_aggregator",
    # Clinical endpoints ontology
    "ClinicalEndpointsOntology",
    "get_clinical_endpoints_ontology",
    # General ontology mappings
    "OntologyLoader",
    "OntologyMappings",
    "get_ontology_loader",
    "get_ontology_mappings",
    # IVA Evidence Report Workflow
    "IVAEvidenceReportWorkflow",
    "generate_iva_evidence_report",
    "EvidenceReportInputs",
    "EvidenceReportOutputs",
    "CEJNarrativePillar",
    "EvidenceStrength",
    "GapStatus",
    # Competitive Graph
    "CompetitiveGraphService",
    # Coverage
    "CoverageService",
    # Feedback
    "FeedbackService",
    "FeedbackType",
    "Feedback",
    # KOL
    "KOLService",
    "KOL",
    # Onboarding
    "OnboardingService",
    # Visualization
    "VisualizationService",
    # Lifecycle
    "LifecycleService",
    "MilestoneType",
    # Global Regulatory
    "GlobalRegulatoryService",
    "RegulatoryRegion",
    "ApprovalStatus",
]
