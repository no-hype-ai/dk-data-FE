"""
Bronze Layer Models

Pydantic models for typed Bronze layer tables extracted from Raw JSON.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from .clinicaltrials import (
    BronzeClinicalTrial,
    BronzeClinicalTrialCreate,
)
from .openfda_labels import (
    BronzeDrugLabel,
    BronzeDrugLabelCreate,
)
from .openfda_faers import (
    BronzeAdverseEvent,
    BronzeAdverseEventCreate,
)
from .chembl import (
    BronzeChemblMolecule,
    BronzeChemblActivity,
)
from .drugbank import (
    BronzeDrugBankDrug,
    BronzeDrugBankInteraction,
)
from .pubchem import (
    BronzePubChemCompound,
)
from .uniprot import (
    BronzeUniProtEntry,
)
from .openalex import (
    BronzeOpenAlexWork,
)

__all__ = [
    # ClinicalTrials
    'BronzeClinicalTrial',
    'BronzeClinicalTrialCreate',
    # OpenFDA Labels
    'BronzeDrugLabel',
    'BronzeDrugLabelCreate',
    # OpenFDA FAERS
    'BronzeAdverseEvent',
    'BronzeAdverseEventCreate',
    # ChEMBL
    'BronzeChemblMolecule',
    'BronzeChemblActivity',
    # DrugBank
    'BronzeDrugBankDrug',
    'BronzeDrugBankInteraction',
    # PubChem
    'BronzePubChemCompound',
    # UniProt
    'BronzeUniProtEntry',
    # OpenAlex
    'BronzeOpenAlexWork',
]
