"""
Bronze UniProt Models

Typed extraction from raw_uniprot JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class BronzeUniProtEntryBase(BaseModel):
    """Base fields for Bronze UniProt entry."""
    accession: str = Field(..., description="Primary UniProt accession")
    secondary_accessions: Optional[List[str]] = None
    entry_name: Optional[str] = None
    
    # Protein info
    protein_name: Optional[str] = None
    protein_names: Optional[List[str]] = None
    gene_names: Optional[List[str]] = None
    organism: Optional[str] = None
    organism_id: Optional[int] = None
    
    # Sequence
    sequence: Optional[str] = None
    sequence_length: Optional[int] = None
    sequence_mass: Optional[int] = None
    sequence_checksum: Optional[str] = None
    
    # Function
    function_comments: Optional[List[str]] = None
    catalytic_activity: Optional[List[Dict[str, Any]]] = None
    pathway: Optional[List[str]] = None
    
    # Subcellular location
    subcellular_location: Optional[List[str]] = None
    
    # Disease involvement
    disease_comments: Optional[List[Dict[str, Any]]] = None
    
    # Cross-references
    pdb_ids: Optional[List[str]] = None
    chembl_target_id: Optional[str] = None
    drugbank_ids: Optional[List[str]] = None
    ensembl_ids: Optional[List[str]] = None
    refseq_ids: Optional[List[str]] = None
    
    # Features
    features: Optional[List[Dict[str, Any]]] = None
    
    # Dates
    entry_version: Optional[int] = None
    sequence_version: Optional[int] = None


class BronzeUniProtEntry(BronzeUniProtEntryBase):
    """Full Bronze UniProt entry model."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_id: UUID
    processed_at: datetime
    created_at: datetime
    updated_at: datetime
    extraction_version: str = "1.0"
