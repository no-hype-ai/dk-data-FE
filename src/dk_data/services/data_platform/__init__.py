"""
DK Molecule Data Platform Services

Core services for the extended Medallion Architecture:
- Raw → Bronze → Silver → Gold data pipeline
- Entity resolution with InChI Key as master identifier
- Cross-source data integration

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

# Entity Resolution
from .identifier_resolver import (
    IdentifierResolver,
    IdentifierType,
    ResolutionResult,
    SOURCE_PRECEDENCE,
    IDENTIFIER_PATTERNS,
)
from .fuzzy_matcher import FuzzyMatcher, FuzzyMatch

# Raw Layer - API ingestion
from .raw_ingestion import (
    RawIngestionService,
    DataSource,
    REFRESH_SCHEDULE,
    ClinicalTrialsIngestion,
    OpenFDAIngestion,
    ChEMBLIngestion,
    PubChemIngestion,
    UniProtIngestion,
    OpenAlexIngestion,
)

# Bronze Layer - JSON extraction
from .raw_to_bronze import BronzeIngestionService, TransformResult

# Silver Layer - Entity resolution and normalization
from .silver_transformation import SilverTransformationService, TransformationResult

# Gold Layer - Aggregation and views
from .gold_aggregation import GoldAggregationService, AggregationResult

# Resolution Queue - Quarantine workflow
from .resolution_queue import (
    ResolutionQueueService,
    ResolutionAction,
    QueuePriority,
    QueueItem,
    ResolutionStats,
)

# Lifecycle Detection
from .lifecycle_detection import (
    LifecycleDetectionService,
    LifecycleStage,
    LifecycleDetectionResult,
    EvidenceItem,
)

# Molecule Onboarding
from .molecule_onboarding import (
    MoleculeOnboardingService,
)

# Alert Service
from .alert_service import (
    AlertService,
    AlertType,
    AlertSeverity,
    Alert,
)

# Data Freshness Monitor
from .data_freshness_monitor import (
    DataFreshnessMonitor,
    RefreshTier,
    SourceStatus,
    SourceFreshness,
    FreshnessReport,
)

# Sync Scheduler
from .sync_scheduler import (
    TieredSyncScheduler,
    SyncPriority,
    ScheduledSync,
    SyncJob,
)

# Evidence Requirements
from .evidence_requirements import (
    EvidenceRequirementService,
    EvidenceType,
    EvidenceRequirement,
    EvidenceResult,
    StageEvidenceReport,
)

# Stage Validation
from .stage_validation import (
    StageValidationService,
    ValidationResult,
    ValidationRecord,
)

# Schema Detection
from .schema_detector import (
    SchemaDetector,
    TableSchema,
    ColumnSchema,
    PostgresType,
)

# Table Generator
from .table_generator import (
    TableGenerator,
    TableGenerationResult,
    DataSourceRegistration,
)

# Dynamic Silver Transformation
from .dynamic_silver_transformation import (
    DynamicSilverTransformation,
    TransformationResult as DynamicTransformationResult,
    register_source,
    transform_source,
)

# SQLMesh Model Generator
from .sqlmesh_model_generator import (
    SQLMeshModelGenerator,
    TransformationRule,
    GeneratedModel,
)

__all__ = [
    # Entity Resolution
    'IdentifierResolver',
    'IdentifierType',
    'ResolutionResult',
    'SOURCE_PRECEDENCE',
    'IDENTIFIER_PATTERNS',
    'FuzzyMatcher',
    'FuzzyMatch',

    # Raw Layer
    'RawIngestionService',
    'DataSource',
    'REFRESH_SCHEDULE',
    'ClinicalTrialsIngestion',
    'OpenFDAIngestion',
    'ChEMBLIngestion',
    'PubChemIngestion',
    'UniProtIngestion',
    'OpenAlexIngestion',

    # Bronze Layer
    'BronzeIngestionService',
    'TransformResult',

    # Silver Layer
    'SilverTransformationService',
    'TransformationResult',

    # Gold Layer
    'GoldAggregationService',
    'AggregationResult',

    # Resolution Queue
    'ResolutionQueueService',
    'ResolutionAction',
    'QueuePriority',
    'QueueItem',
    'ResolutionStats',

    # Lifecycle Detection
    'LifecycleDetectionService',
    'LifecycleStage',
    'LifecycleDetectionResult',
    'EvidenceItem',

    # Molecule Onboarding
    'MoleculeOnboardingService',

    # Alert Service
    'AlertService',
    'AlertType',
    'AlertSeverity',
    'Alert',

    # Data Freshness Monitor
    'DataFreshnessMonitor',
    'RefreshTier',
    'SourceStatus',
    'SourceFreshness',
    'FreshnessReport',

    # Sync Scheduler
    'TieredSyncScheduler',
    'SyncPriority',
    'ScheduledSync',
    'SyncJob',

    # Evidence Requirements
    'EvidenceRequirementService',
    'EvidenceType',
    'EvidenceRequirement',
    'EvidenceResult',
    'StageEvidenceReport',

    # Stage Validation
    'StageValidationService',
    'ValidationResult',
    'ValidationRecord',

    # Schema Detection
    'SchemaDetector',
    'TableSchema',
    'ColumnSchema',
    'PostgresType',

    # Table Generator
    'TableGenerator',
    'TableGenerationResult',
    'DataSourceRegistration',

    # Dynamic Silver Transformation
    'DynamicSilverTransformation',
    'DynamicTransformationResult',
    'register_source',
    'transform_source',

    # SQLMesh Model Generator
    'SQLMeshModelGenerator',
    'TransformationRule',
    'GeneratedModel',
]
