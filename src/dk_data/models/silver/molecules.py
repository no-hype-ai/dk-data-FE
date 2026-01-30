"""
Silver Molecule Models

Pydantic models for the Silver molecules table.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class DevelopmentStatus(str, Enum):
    """Molecule development status."""
    UNKNOWN = "unknown"
    PRECLINICAL = "preclinical"
    PHASE_1 = "phase_1"
    PHASE_2 = "phase_2"
    PHASE_3 = "phase_3"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


class MoleculeType(str, Enum):
    """Molecule type classification."""
    SMALL_MOLECULE = "small_molecule"
    PROTEIN = "protein"
    ANTIBODY = "antibody"
    PEPTIDE = "peptide"
    OLIGONUCLEOTIDE = "oligonucleotide"
    CELL_THERAPY = "cell_therapy"
    GENE_THERAPY = "gene_therapy"
    VACCINE = "vaccine"
    UNKNOWN = "unknown"


class MoleculeBase(BaseModel):
    """Base molecule fields."""
    inchi_key: Optional[str] = Field(None, max_length=27, pattern=r'^[A-Z]{14}-[A-Z]{10}-[A-Z]$')
    canonical_name: str = Field(..., max_length=500)
    canonical_smiles: Optional[str] = None
    inchi: Optional[str] = None
    molecular_formula: Optional[str] = Field(None, max_length=200)
    molecular_weight: Optional[float] = Field(None, ge=0)
    molecule_type: Optional[MoleculeType] = None
    therapeutic_areas: Optional[List[str]] = None
    mechanism_of_action: Optional[str] = None
    development_status: Optional[DevelopmentStatus] = None
    max_phase: Optional[int] = Field(None, ge=0, le=4)
    first_approval_year: Optional[int] = Field(None, ge=1900, le=2100)
    approval_date: Optional[date] = None


class MoleculeCreate(MoleculeBase):
    """Model for creating a new molecule."""
    name_source: Optional[str] = None
    data_sources: Optional[List[str]] = None
    primary_source: Optional[str] = None


class MoleculeUpdate(BaseModel):
    """Model for updating a molecule."""
    canonical_name: Optional[str] = Field(None, max_length=500)
    canonical_smiles: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    molecule_type: Optional[MoleculeType] = None
    therapeutic_areas: Optional[List[str]] = None
    mechanism_of_action: Optional[str] = None
    development_status: Optional[DevelopmentStatus] = None
    max_phase: Optional[int] = None
    needs_review: Optional[bool] = None
    review_reason: Optional[str] = None


class Molecule(MoleculeBase):
    """Full molecule model from database."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name_source: Optional[str] = None
    resolution_confidence: float = Field(default=1.0, ge=0, le=1)
    needs_review: bool = False
    review_reason: Optional[str] = None
    data_sources: Optional[List[str]] = None
    primary_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MoleculeWithIdentifiers(Molecule):
    """Molecule with cross-reference identifiers."""
    drugbank_id: Optional[str] = None
    chembl_id: Optional[str] = None
    pubchem_cid: Optional[int] = None
    unii: Optional[str] = None
    cas_number: Optional[str] = None
    rxcui: Optional[str] = None
    aliases: Optional[List[str]] = None


class MoleculeSearchResult(BaseModel):
    """Molecule search result."""
    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str
    similarity: float
    match_type: str


class IdentifierMapping(BaseModel):
    """Identifier mapping model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID
    identifier_type: str
    identifier_value: str
    source: str
    confidence: float = 1.0
    is_primary: bool = False
    is_validated: bool = False
    validated_at: Optional[datetime] = None
    validated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MoleculeAlias(BaseModel):
    """Molecule alias model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID
    alias_name: str
    alias_type: str
    alias_name_normalized: Optional[str] = None
    region: Optional[str] = None
    language: str = "en"
    source: str
    created_at: datetime
