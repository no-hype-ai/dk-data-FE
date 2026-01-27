"""
Indication and ICD-10 Data Models.

Models for representing medical indications, ICD-10 codes,
and their hierarchical relationships.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ICD10Level(Enum):
    """Level in the ICD-10 hierarchy."""

    CHAPTER = 1      # e.g., "C" (Neoplasms)
    BLOCK = 2        # e.g., "C00-C14" (Malignant neoplasms of lip, oral cavity...)
    CATEGORY = 3     # e.g., "C50" (Malignant neoplasm of breast)
    SUBCATEGORY = 4  # e.g., "C50.9" (Breast, unspecified)
    CODE = 5         # e.g., "C50.911" (Malignant neoplasm of unspecified site...)


class IndicationStatus(str, Enum):
    """Status of an indication for a drug."""

    APPROVED = "approved"           # FDA-approved indication
    UNDER_REVIEW = "under_review"   # Submitted to FDA
    CLINICAL_TRIAL = "clinical_trial"  # Being studied in trials
    OFF_LABEL = "off_label"         # Used but not approved
    DISCONTINUED = "discontinued"   # No longer pursued


class IndicationSource(str, Enum):
    """Source of indication information."""

    FDA_LABEL = "fda_label"
    CLINICALTRIALS = "clinicaltrials"
    DRUGBANK = "drugbank"
    CHEMBL = "chembl"
    MANUAL = "manual"


@dataclass
class ICD10Code:
    """
    An ICD-10 code with hierarchical information.

    ICD-10 codes follow a hierarchical structure:
    - Chapter: Single letter (A-Z, excluding U)
    - Block: Letter + range (e.g., A00-A09)
    - Category: 3 characters (e.g., A00)
    - Subcategory: 4+ characters (e.g., A00.0, A00.1)
    """

    code: str  # The ICD-10 code (e.g., "M05.79")
    description: str  # Human-readable description
    level: ICD10Level = ICD10Level.CODE

    # Hierarchy
    parent_code: Optional[str] = None
    chapter: Optional[str] = None  # Chapter letter (e.g., "M")
    block: Optional[str] = None    # Block code (e.g., "M05-M14")
    category: Optional[str] = None # Category code (e.g., "M05")

    # Metadata
    is_billable: bool = True  # Can be used for billing
    includes: List[str] = field(default_factory=list)  # Included conditions
    excludes: List[str] = field(default_factory=list)  # Excluded conditions

    # UMLS mapping
    umls_cui: Optional[str] = None  # Concept Unique Identifier

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ICD10Code):
            return False
        return self.code == other.code

    def get_parent_codes(self) -> List[str]:
        """
        Get all parent codes in the hierarchy.

        Example: M05.79 -> [M05.7, M05, M05-M14, M]
        """
        parents = []
        if self.parent_code:
            parents.append(self.parent_code)
        if self.category and self.category != self.code:
            parents.append(self.category)
        if self.block:
            parents.append(self.block)
        if self.chapter:
            parents.append(self.chapter)
        return parents

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "code": self.code,
            "description": self.description,
            "level": self.level.value,
            "parent_code": self.parent_code,
            "chapter": self.chapter,
            "block": self.block,
            "category": self.category,
            "is_billable": self.is_billable,
            "includes": self.includes,
            "excludes": self.excludes,
            "umls_cui": self.umls_cui,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ICD10Code":
        """Create from dictionary."""
        return cls(
            code=data["code"],
            description=data["description"],
            level=ICD10Level(data.get("level", 5)),
            parent_code=data.get("parent_code"),
            chapter=data.get("chapter"),
            block=data.get("block"),
            category=data.get("category"),
            is_billable=data.get("is_billable", True),
            includes=data.get("includes", []),
            excludes=data.get("excludes", []),
            umls_cui=data.get("umls_cui"),
        )

    @staticmethod
    def parse_code_level(code: str) -> ICD10Level:
        """
        Determine the level of an ICD-10 code from its format.

        Args:
            code: ICD-10 code string

        Returns:
            ICD10Level indicating the hierarchy level
        """
        if len(code) == 1 and code.isalpha():
            return ICD10Level.CHAPTER
        if "-" in code:
            return ICD10Level.BLOCK
        if len(code) == 3:
            return ICD10Level.CATEGORY
        if len(code) == 4 or (len(code) == 5 and code[3] == "."):
            return ICD10Level.SUBCATEGORY
        return ICD10Level.CODE


@dataclass
class Indication:
    """
    A medical indication for a drug.

    Represents a disease, condition, or symptom that a drug
    is used to treat, diagnose, prevent, or cure.
    """

    # Core identifiers
    id: str  # Internal unique ID
    name: str  # Primary name (e.g., "Rheumatoid Arthritis")
    normalized_name: Optional[str] = None  # Standardized form

    # Coding
    icd10_codes: List[str] = field(default_factory=list)  # Associated ICD-10 codes
    mesh_terms: List[str] = field(default_factory=list)   # MeSH descriptors
    umls_cuis: List[str] = field(default_factory=list)    # UMLS Concept IDs
    snomed_codes: List[str] = field(default_factory=list) # SNOMED-CT codes

    # Classification
    therapeutic_area: Optional[str] = None  # e.g., "Immunology", "Oncology"
    disease_category: Optional[str] = None  # Broader category
    is_rare_disease: bool = False
    is_orphan_indication: bool = False

    # Epidemiology
    prevalence: Optional[float] = None  # Estimated prevalence
    incidence: Optional[float] = None   # Estimated incidence
    affected_population: Optional[str] = None  # e.g., "Adults 18+"

    # Source tracking
    source: IndicationSource = IndicationSource.MANUAL
    source_id: Optional[str] = None  # ID in source system
    confidence: float = 1.0  # Confidence in mapping

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Additional data
    synonyms: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Indication):
            return False
        return self.id == other.id

    def get_all_codes(self) -> Set[str]:
        """Get all associated codes from all coding systems."""
        codes = set()
        codes.update(self.icd10_codes)
        codes.update(self.mesh_terms)
        codes.update(self.umls_cuis)
        codes.update(self.snomed_codes)
        return codes

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "icd10_codes": self.icd10_codes,
            "mesh_terms": self.mesh_terms,
            "umls_cuis": self.umls_cuis,
            "snomed_codes": self.snomed_codes,
            "therapeutic_area": self.therapeutic_area,
            "disease_category": self.disease_category,
            "is_rare_disease": self.is_rare_disease,
            "is_orphan_indication": self.is_orphan_indication,
            "prevalence": self.prevalence,
            "incidence": self.incidence,
            "affected_population": self.affected_population,
            "source": self.source.value,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "synonyms": self.synonyms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Indication":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            normalized_name=data.get("normalized_name"),
            icd10_codes=data.get("icd10_codes", []),
            mesh_terms=data.get("mesh_terms", []),
            umls_cuis=data.get("umls_cuis", []),
            snomed_codes=data.get("snomed_codes", []),
            therapeutic_area=data.get("therapeutic_area"),
            disease_category=data.get("disease_category"),
            is_rare_disease=data.get("is_rare_disease", False),
            is_orphan_indication=data.get("is_orphan_indication", False),
            prevalence=data.get("prevalence"),
            incidence=data.get("incidence"),
            affected_population=data.get("affected_population"),
            source=IndicationSource(data.get("source", "manual")),
            source_id=data.get("source_id"),
            confidence=data.get("confidence", 1.0),
            synonyms=data.get("synonyms", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DrugIndication:
    """
    Association between a drug and an indication.

    Represents the relationship between a specific drug/molecule
    and a medical indication, including approval status and evidence.
    """

    drug_id: str  # Reference to drug/molecule
    indication_id: str  # Reference to indication

    # Status
    status: IndicationStatus = IndicationStatus.CLINICAL_TRIAL
    approval_date: Optional[datetime] = None
    approval_region: Optional[str] = None  # e.g., "US", "EU", "Global"

    # Clinical context
    line_of_therapy: Optional[str] = None  # e.g., "first-line", "second-line"
    patient_population: Optional[str] = None  # e.g., "Adult patients with..."
    combination_therapy: bool = False
    combination_drugs: List[str] = field(default_factory=list)

    # Evidence
    clinical_trials: List[str] = field(default_factory=list)  # NCT IDs
    evidence_level: Optional[str] = None  # e.g., "Phase 3", "Real-world"
    efficacy_data: Dict[str, Any] = field(default_factory=dict)

    # Source tracking
    source: IndicationSource = IndicationSource.MANUAL
    source_url: Optional[str] = None
    confidence: float = 1.0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __hash__(self) -> int:
        return hash((self.drug_id, self.indication_id))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DrugIndication):
            return False
        return (
            self.drug_id == other.drug_id
            and self.indication_id == other.indication_id
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "drug_id": self.drug_id,
            "indication_id": self.indication_id,
            "status": self.status.value,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "approval_region": self.approval_region,
            "line_of_therapy": self.line_of_therapy,
            "patient_population": self.patient_population,
            "combination_therapy": self.combination_therapy,
            "combination_drugs": self.combination_drugs,
            "clinical_trials": self.clinical_trials,
            "evidence_level": self.evidence_level,
            "efficacy_data": self.efficacy_data,
            "source": self.source.value,
            "source_url": self.source_url,
            "confidence": self.confidence,
        }


@dataclass
class ICD10Hierarchy:
    """
    Complete ICD-10 code hierarchy for navigation and expansion.

    Caches the parent-child relationships for efficient
    hierarchy traversal during graph expansion.
    """

    # Root node (usually a chapter or category)
    root_code: str

    # All codes in this hierarchy branch
    codes: Dict[str, ICD10Code] = field(default_factory=dict)

    # Parent -> Children mapping
    children_map: Dict[str, List[str]] = field(default_factory=dict)

    # Metadata
    loaded_at: datetime = field(default_factory=datetime.utcnow)

    def add_code(self, code: ICD10Code) -> None:
        """Add a code to the hierarchy."""
        self.codes[code.code] = code

        # Update children mapping
        if code.parent_code:
            if code.parent_code not in self.children_map:
                self.children_map[code.parent_code] = []
            if code.code not in self.children_map[code.parent_code]:
                self.children_map[code.parent_code].append(code.code)

    def get_children(self, code: str) -> List[ICD10Code]:
        """Get direct children of a code."""
        child_codes = self.children_map.get(code, [])
        return [self.codes[c] for c in child_codes if c in self.codes]

    def get_descendants(self, code: str, max_depth: int = 10) -> List[ICD10Code]:
        """Get all descendants of a code up to max_depth."""
        descendants = []
        to_visit = [(code, 0)]
        visited = set()

        while to_visit:
            current, depth = to_visit.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            for child_code in self.children_map.get(current, []):
                if child_code in self.codes:
                    descendants.append(self.codes[child_code])
                    to_visit.append((child_code, depth + 1))

        return descendants

    def get_ancestors(self, code: str) -> List[ICD10Code]:
        """Get all ancestors of a code (parents up to root)."""
        ancestors = []
        current = self.codes.get(code)

        while current and current.parent_code:
            parent = self.codes.get(current.parent_code)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break

        return ancestors

    def get_siblings(self, code: str) -> List[ICD10Code]:
        """Get sibling codes (same parent)."""
        current = self.codes.get(code)
        if not current or not current.parent_code:
            return []

        siblings = []
        for sibling_code in self.children_map.get(current.parent_code, []):
            if sibling_code != code and sibling_code in self.codes:
                siblings.append(self.codes[sibling_code])

        return siblings

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "root_code": self.root_code,
            "codes": {k: v.to_dict() for k, v in self.codes.items()},
            "children_map": self.children_map,
            "loaded_at": self.loaded_at.isoformat(),
        }


@dataclass
class IndicationOverlap:
    """
    Represents overlap between two drugs' indications.

    Used for calculating competitive relationships based on
    shared indications.
    """

    drug_a_id: str
    drug_b_id: str

    # Overlap metrics
    shared_indications: List[str] = field(default_factory=list)
    shared_icd10_codes: List[str] = field(default_factory=list)

    # Jaccard similarity scores
    indication_jaccard: float = 0.0  # |A∩B| / |A∪B| for indications
    icd10_jaccard: float = 0.0       # |A∩B| / |A∪B| for ICD-10 codes

    # Weighted overlap (considers hierarchy)
    weighted_overlap: float = 0.0

    # Details
    drug_a_indication_count: int = 0
    drug_b_indication_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "drug_a_id": self.drug_a_id,
            "drug_b_id": self.drug_b_id,
            "shared_indications": self.shared_indications,
            "shared_icd10_codes": self.shared_icd10_codes,
            "indication_jaccard": self.indication_jaccard,
            "icd10_jaccard": self.icd10_jaccard,
            "weighted_overlap": self.weighted_overlap,
            "drug_a_indication_count": self.drug_a_indication_count,
            "drug_b_indication_count": self.drug_b_indication_count,
        }
