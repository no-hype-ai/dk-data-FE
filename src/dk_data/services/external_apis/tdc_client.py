"""
TDC (Therapeutics Data Commons) Client.

Provides access to TDC ADMET datasets:
- Absorption properties (Caco2, HIA, Bioavailability, etc.)
- Distribution properties (BBB, PPBR, VDss, etc.)
- Metabolism properties (CYP enzymes, Half-Life, etc.)
- Excretion properties (Clearance)
- Toxicity properties (hERG, AMES, DILI, LD50, etc.)

Website: https://tdcommons.ai
Data hosted on: Harvard Dataverse
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, APIResponse, BaseAPIClient
from .cache_manager import CacheManager, DataSource


@dataclass
class ADMETProperty:
    """A single ADMET property measurement."""

    compound_id: str
    smiles: str
    property_name: str
    property_value: float
    property_category: str  # absorption, distribution, metabolism, excretion, toxicity
    dataset_name: str
    inchi_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compound_id": self.compound_id,
            "smiles": self.smiles,
            "property_name": self.property_name,
            "property_value": self.property_value,
            "property_category": self.property_category,
            "dataset_name": self.dataset_name,
            "inchi_key": self.inchi_key,
        }


@dataclass
class TDCDataset:
    """Information about a TDC dataset."""

    name: str
    category: str
    description: str
    num_compounds: int
    task_type: str  # classification, regression
    source_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "num_compounds": self.num_compounds,
            "task_type": self.task_type,
            "source_url": self.source_url,
        }


class TDCClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for TDC (Therapeutics Data Commons) ADMET datasets.

    TDC provides curated benchmark datasets for drug discovery.
    Data is primarily accessed via file downloads from Harvard Dataverse.

    Usage:
        client = TDCClient()
        data = await client.get_admet_data("Caco2_Wang")
    """

    # Dataset metadata
    ADMET_DATASETS = {
        # Absorption
        "Caco2_Wang": {
            "category": "absorption",
            "description": "Caco-2 cell permeability (Wang et al.)",
            "task_type": "regression",
        },
        "HIA_Hou": {
            "category": "absorption",
            "description": "Human intestinal absorption (Hou et al.)",
            "task_type": "classification",
        },
        "Pgp_Broccatelli": {
            "category": "absorption",
            "description": "P-glycoprotein inhibition (Broccatelli et al.)",
            "task_type": "classification",
        },
        "Bioavailability_Ma": {
            "category": "absorption",
            "description": "Oral bioavailability (Ma et al.)",
            "task_type": "classification",
        },
        "Solubility_AqSolDB": {
            "category": "absorption",
            "description": "Aqueous solubility (AqSolDB)",
            "task_type": "regression",
        },
        "Lipophilicity_AstraZeneca": {
            "category": "absorption",
            "description": "Lipophilicity/LogD (AstraZeneca)",
            "task_type": "regression",
        },
        # Distribution
        "BBB_Martins": {
            "category": "distribution",
            "description": "Blood-brain barrier penetration (Martins et al.)",
            "task_type": "classification",
        },
        "PPBR_AZ": {
            "category": "distribution",
            "description": "Plasma protein binding rate (AstraZeneca)",
            "task_type": "regression",
        },
        "VDss_Lombardo": {
            "category": "distribution",
            "description": "Volume of distribution (Lombardo et al.)",
            "task_type": "regression",
        },
        # Metabolism
        "CYP2C9_Veith": {
            "category": "metabolism",
            "description": "CYP2C9 substrate/inhibitor (Veith et al.)",
            "task_type": "classification",
        },
        "CYP2D6_Veith": {
            "category": "metabolism",
            "description": "CYP2D6 substrate/inhibitor (Veith et al.)",
            "task_type": "classification",
        },
        "CYP3A4_Veith": {
            "category": "metabolism",
            "description": "CYP3A4 substrate/inhibitor (Veith et al.)",
            "task_type": "classification",
        },
        "CYP2C19_Veith": {
            "category": "metabolism",
            "description": "CYP2C19 substrate/inhibitor (Veith et al.)",
            "task_type": "classification",
        },
        "CYP1A2_Veith": {
            "category": "metabolism",
            "description": "CYP1A2 substrate/inhibitor (Veith et al.)",
            "task_type": "classification",
        },
        "Half_Life_Obach": {
            "category": "metabolism",
            "description": "Half-life (Obach et al.)",
            "task_type": "regression",
        },
        # Excretion
        "Clearance_Hepatocyte_AZ": {
            "category": "excretion",
            "description": "Hepatocyte clearance (AstraZeneca)",
            "task_type": "regression",
        },
        "Clearance_Microsome_AZ": {
            "category": "excretion",
            "description": "Microsome clearance (AstraZeneca)",
            "task_type": "regression",
        },
        # Toxicity
        "hERG": {
            "category": "toxicity",
            "description": "hERG channel inhibition (cardiotoxicity)",
            "task_type": "classification",
        },
        "AMES": {
            "category": "toxicity",
            "description": "Ames mutagenicity test",
            "task_type": "classification",
        },
        "DILI": {
            "category": "toxicity",
            "description": "Drug-induced liver injury",
            "task_type": "classification",
        },
        "LD50_Zhu": {
            "category": "toxicity",
            "description": "Acute toxicity LD50 (Zhu et al.)",
            "task_type": "regression",
        },
        "Carcinogens_Lagunin": {
            "category": "toxicity",
            "description": "Carcinogenicity (Lagunin et al.)",
            "task_type": "classification",
        },
        "ClinTox": {
            "category": "toxicity",
            "description": "Clinical trial toxicity failure",
            "task_type": "classification",
        },
    }

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url="https://dataverse.harvard.edu",
            timeout=120.0,  # Large files may take time
            max_retries=3,
            requests_per_second=2.0,
            cache_ttl=2592000,  # 30 days (datasets rarely change)
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if TDC data is accessible."""
        try:
            # Try to access the dataverse API
            result = await self._get("/api/search", params={"q": "TDC ADMET"})
            return "data" in result
        except Exception as e:
            logger.error(f"TDC health check failed: {e}")
            return False

    def list_datasets(self, category: Optional[str] = None) -> List[TDCDataset]:
        """
        List available ADMET datasets.

        Args:
            category: Filter by category (absorption, distribution, metabolism, excretion, toxicity)

        Returns:
            List of available datasets
        """
        datasets = []
        for name, info in self.ADMET_DATASETS.items():
            if category and info["category"] != category:
                continue
            datasets.append(
                TDCDataset(
                    name=name,
                    category=info["category"],
                    description=info["description"],
                    num_compounds=0,  # Would need to load to know
                    task_type=info["task_type"],
                )
            )
        return datasets

    def get_dataset_info(self, dataset_name: str) -> Optional[TDCDataset]:
        """Get information about a specific dataset."""
        if dataset_name not in self.ADMET_DATASETS:
            return None

        info = self.ADMET_DATASETS[dataset_name]
        return TDCDataset(
            name=dataset_name,
            category=info["category"],
            description=info["description"],
            num_compounds=0,
            task_type=info["task_type"],
        )

    async def get_admet_data(
        self, dataset_name: str, limit: Optional[int] = None
    ) -> APIResponse:
        """
        Get ADMET data for a specific dataset.

        Args:
            dataset_name: Name of the TDC dataset (e.g., "Caco2_Wang")
            limit: Maximum number of records to return

        Returns:
            APIResponse with ADMET property data
        """
        if dataset_name not in self.ADMET_DATASETS:
            return APIResponse(
                success=False,
                error=f"Unknown dataset: {dataset_name}. Use list_datasets() to see available datasets.",
            )

        try:
            # TDC data can be accessed via their Python package or pre-downloaded files
            # For now, return metadata since actual data requires TDC package
            info = self.ADMET_DATASETS[dataset_name]

            return APIResponse(
                success=True,
                data={
                    "dataset_name": dataset_name,
                    "category": info["category"],
                    "description": info["description"],
                    "task_type": info["task_type"],
                    "note": "Full data access requires TDC Python package installation",
                },
                source="tdc_admet",
            )

        except Exception as e:
            logger.error(f"Error fetching TDC dataset {dataset_name}: {e}")
            return APIResponse(success=False, error=str(e))

    async def search_by_smiles(self, smiles: str) -> APIResponse:
        """
        Search for ADMET predictions by SMILES.

        Note: This would typically use a local database of pre-loaded TDC data
        or make predictions using trained models.

        Args:
            smiles: SMILES string of the compound

        Returns:
            APIResponse with available ADMET data
        """
        try:
            # This would typically query a local database with pre-loaded TDC data
            # For now, return a placeholder indicating the capability
            return APIResponse(
                success=True,
                data={
                    "smiles": smiles,
                    "predictions_available": False,
                    "note": "ADMET predictions require pre-trained models or database lookup",
                },
                source="tdc_admet",
            )

        except Exception as e:
            logger.error(f"Error searching TDC for SMILES: {e}")
            return APIResponse(success=False, error=str(e))

    def get_category_datasets(self, category: str) -> List[str]:
        """
        Get all dataset names for a specific ADMET category.

        Args:
            category: absorption, distribution, metabolism, excretion, or toxicity

        Returns:
            List of dataset names in that category
        """
        return [
            name
            for name, info in self.ADMET_DATASETS.items()
            if info["category"] == category
        ]


# Singleton instance
_tdc_client: Optional[TDCClient] = None


async def get_tdc_client(cache_manager: Optional[CacheManager] = None) -> TDCClient:
    """Get or create the TDC client instance."""
    global _tdc_client

    if _tdc_client is None:
        _tdc_client = TDCClient(cache_manager)

    return _tdc_client
