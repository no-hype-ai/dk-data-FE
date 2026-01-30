"""
CMS Medicare API Client.

Provides access to CMS (Centers for Medicare & Medicaid Services) public data:
- Medicare Part D drug spending and utilization
- Prescriber-level data
- Drug costs and trends

API Documentation: https://data.cms.gov/
Rate Limit: No strict limit, but respectful usage recommended
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class DrugUtilization:
    """Medicare drug utilization data."""

    # Drug identifiers
    ndc_code: Optional[str] = None
    brand_name: Optional[str] = None
    generic_name: Optional[str] = None
    labeler_name: Optional[str] = None  # Manufacturer

    # Time period
    year: Optional[int] = None
    quarter: Optional[int] = None

    # Utilization metrics
    total_claims: Optional[int] = None
    total_beneficiaries: Optional[int] = None
    total_supply_days: Optional[int] = None
    total_units: Optional[float] = None

    # Cost metrics
    total_spending: Optional[float] = None
    average_cost_per_claim: Optional[float] = None
    average_cost_per_day: Optional[float] = None
    average_cost_per_beneficiary: Optional[float] = None

    # Part D specific
    part_d_claims: Optional[int] = None
    part_d_spending: Optional[float] = None
    low_income_subsidy_claims: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ndc_code": self.ndc_code,
            "brand_name": self.brand_name,
            "generic_name": self.generic_name,
            "labeler_name": self.labeler_name,
            "year": self.year,
            "quarter": self.quarter,
            "total_claims": self.total_claims,
            "total_beneficiaries": self.total_beneficiaries,
            "total_supply_days": self.total_supply_days,
            "total_units": self.total_units,
            "total_spending": self.total_spending,
            "average_cost_per_claim": self.average_cost_per_claim,
            "average_cost_per_day": self.average_cost_per_day,
            "average_cost_per_beneficiary": self.average_cost_per_beneficiary,
            "part_d_claims": self.part_d_claims,
            "part_d_spending": self.part_d_spending,
            "low_income_subsidy_claims": self.low_income_subsidy_claims,
        }


@dataclass
class PrescriberData:
    """Medicare prescriber-level data."""

    # Prescriber identifiers
    npi: Optional[str] = None
    prescriber_name: Optional[str] = None
    prescriber_last_name: Optional[str] = None
    prescriber_first_name: Optional[str] = None

    # Location
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    # Specialty
    specialty: Optional[str] = None

    # Drug specific
    drug_name: Optional[str] = None
    generic_name: Optional[str] = None

    # Prescribing metrics
    total_claims: Optional[int] = None
    total_30_day_fills: Optional[int] = None
    total_supply_days: Optional[int] = None
    total_beneficiaries: Optional[int] = None

    # Cost metrics
    total_cost: Optional[float] = None

    # Year
    year: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npi": self.npi,
            "prescriber_name": self.prescriber_name,
            "prescriber_last_name": self.prescriber_last_name,
            "prescriber_first_name": self.prescriber_first_name,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "specialty": self.specialty,
            "drug_name": self.drug_name,
            "generic_name": self.generic_name,
            "total_claims": self.total_claims,
            "total_30_day_fills": self.total_30_day_fills,
            "total_supply_days": self.total_supply_days,
            "total_beneficiaries": self.total_beneficiaries,
            "total_cost": self.total_cost,
            "year": self.year,
        }


@dataclass
class PartDSpending:
    """Medicare Part D spending data for a drug."""

    # Drug identifiers
    brand_name: str
    generic_name: Optional[str] = None

    # Coverage
    coverage_type: Optional[str] = None  # Brand, Generic, etc.

    # Annual metrics
    year: Optional[int] = None

    # Spending metrics
    total_spending: Optional[float] = None
    total_spending_per_user: Optional[float] = None
    total_claims: Optional[int] = None
    total_beneficiaries: Optional[int] = None

    # Cost metrics
    average_cost_per_unit: Optional[float] = None
    average_cost_per_claim: Optional[float] = None

    # Change metrics
    spending_change_pct: Optional[float] = None  # Year-over-year change
    cost_per_unit_change_pct: Optional[float] = None
    beneficiary_change_pct: Optional[float] = None

    # Out-of-pocket
    beneficiary_cost: Optional[float] = None
    beneficiary_cost_share_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "generic_name": self.generic_name,
            "coverage_type": self.coverage_type,
            "year": self.year,
            "total_spending": self.total_spending,
            "total_spending_per_user": self.total_spending_per_user,
            "total_claims": self.total_claims,
            "total_beneficiaries": self.total_beneficiaries,
            "average_cost_per_unit": self.average_cost_per_unit,
            "average_cost_per_claim": self.average_cost_per_claim,
            "spending_change_pct": self.spending_change_pct,
            "cost_per_unit_change_pct": self.cost_per_unit_change_pct,
            "beneficiary_change_pct": self.beneficiary_change_pct,
            "beneficiary_cost": self.beneficiary_cost,
            "beneficiary_cost_share_pct": self.beneficiary_cost_share_pct,
        }


class CMSMedicareClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for CMS Medicare Public Data APIs.

    Provides access to Medicare drug spending, utilization, and prescriber data
    through the CMS Open Data portal.

    Usage:
        client = CMSMedicareClient()
        util = await client.get_drug_utilization("12345-6789", year=2023)
        prescribers = await client.get_prescriber_data("Humira")
        spending = await client.get_part_d_spending("Keytruda")
    """

    # CMS Data API endpoints
    # Using Socrata Open Data API (SODA) format
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset"

    # Dataset identifiers (these may need to be updated as CMS updates their data)
    # Part D Spending by Drug: https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug
    DATASET_PART_D_SPENDING = "e2c5-9e4n"

    # Medicare Part D Prescribers by Provider and Drug
    DATASET_PRESCRIBERS = "dntg-wkjw"

    # State Drug Utilization Data (Medicaid)
    DATASET_DRUG_UTILIZATION = "tau9-gfwr"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=60.0,  # CMS queries can be slow
            max_retries=3,
            requests_per_second=2.0,  # Respectful rate limit
            cache_ttl=604800,  # 7 days - CMS data updates weekly/quarterly
            headers={
                "Accept": "application/json",
            },
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if CMS API is accessible."""
        try:
            # Try to get dataset info
            result = await self._get(
                f"/{self.DATASET_PART_D_SPENDING}/data",
                params={"size": 1},
                use_cache=False
            )
            return isinstance(result, list) or "data" in result
        except Exception as e:
            logger.error(f"CMS Medicare health check failed: {e}")
            return False

    async def get_drug_utilization(
        self,
        ndc_code: Optional[str] = None,
        drug_name: Optional[str] = None,
        year: Optional[int] = None,
        state: Optional[str] = None,
        limit: int = 100
    ) -> List[DrugUtilization]:
        """
        Get drug utilization data from Medicaid State Drug Utilization.

        Args:
            ndc_code: National Drug Code
            drug_name: Drug brand or generic name
            year: Year of data
            state: State abbreviation
            limit: Maximum results

        Returns:
            List of drug utilization records
        """
        filters = []

        if ndc_code:
            filters.append(f"ndc=\"{ndc_code}\"")
        if drug_name:
            # Search both brand and generic name
            filters.append(f"(product_name like \"%{drug_name}%\" OR labeler_name like \"%{drug_name}%\")")
        if year:
            filters.append(f"year={year}")
        if state:
            filters.append(f"state=\"{state}\"")

        params = {
            "size": min(limit, 1000),
        }

        if filters:
            params["filter"] = " AND ".join(filters)

        try:
            result = await self._get(
                f"/{self.DATASET_DRUG_UTILIZATION}/data",
                params=params
            )

            utilizations = []
            data = result if isinstance(result, list) else result.get("data", [])

            for item in data:
                util = DrugUtilization(
                    ndc_code=item.get("ndc"),
                    brand_name=item.get("product_name"),
                    labeler_name=item.get("labeler_name"),
                    year=self._safe_int(item.get("year")),
                    quarter=self._safe_int(item.get("quarter")),
                    total_claims=self._safe_int(item.get("number_of_prescriptions")),
                    total_units=self._safe_float(item.get("units_reimbursed")),
                    total_spending=self._safe_float(item.get("total_amount_reimbursed")),
                )
                utilizations.append(util)

            return utilizations
        except Exception as e:
            logger.error(f"Error getting CMS drug utilization: {e}")
            return []

    async def get_prescriber_data(
        self,
        drug_name: str,
        specialty: Optional[str] = None,
        state: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 100
    ) -> List[PrescriberData]:
        """
        Get prescriber-level data for a drug.

        Args:
            drug_name: Drug brand or generic name
            specialty: Prescriber specialty filter
            state: State abbreviation filter
            year: Year of data
            limit: Maximum results

        Returns:
            List of prescriber data records
        """
        filters = [f"(brnd_name like \"%{drug_name}%\" OR gnrc_name like \"%{drug_name}%\")"]

        if specialty:
            filters.append(f"prscrbr_type like \"%{specialty}%\"")
        if state:
            filters.append(f"prscrbr_state_abrvtn=\"{state}\"")
        if year:
            filters.append(f"year={year}")

        params = {
            "size": min(limit, 1000),
            "filter": " AND ".join(filters),
        }

        try:
            result = await self._get(
                f"/{self.DATASET_PRESCRIBERS}/data",
                params=params
            )

            prescribers = []
            data = result if isinstance(result, list) else result.get("data", [])

            for item in data:
                prescriber = PrescriberData(
                    npi=item.get("prscrbr_npi"),
                    prescriber_last_name=item.get("prscrbr_last_org_name"),
                    prescriber_first_name=item.get("prscrbr_first_name"),
                    city=item.get("prscrbr_city"),
                    state=item.get("prscrbr_state_abrvtn"),
                    zip_code=item.get("prscrbr_zip5"),
                    specialty=item.get("prscrbr_type"),
                    drug_name=item.get("brnd_name"),
                    generic_name=item.get("gnrc_name"),
                    total_claims=self._safe_int(item.get("tot_clms")),
                    total_30_day_fills=self._safe_int(item.get("tot_30day_fills")),
                    total_supply_days=self._safe_int(item.get("tot_day_suply")),
                    total_beneficiaries=self._safe_int(item.get("tot_benes")),
                    total_cost=self._safe_float(item.get("tot_drug_cst")),
                    year=self._safe_int(item.get("year")),
                )

                # Construct full name
                if prescriber.prescriber_last_name and prescriber.prescriber_first_name:
                    prescriber.prescriber_name = f"{prescriber.prescriber_first_name} {prescriber.prescriber_last_name}"
                elif prescriber.prescriber_last_name:
                    prescriber.prescriber_name = prescriber.prescriber_last_name

                prescribers.append(prescriber)

            return prescribers
        except Exception as e:
            logger.error(f"Error getting CMS prescriber data for '{drug_name}': {e}")
            return []

    async def get_part_d_spending(
        self,
        drug_name: str,
        year: Optional[int] = None,
        limit: int = 50
    ) -> List[PartDSpending]:
        """
        Get Medicare Part D spending data for a drug.

        Args:
            drug_name: Drug brand or generic name
            year: Year of data
            limit: Maximum results

        Returns:
            List of Part D spending records
        """
        filters = [f"(brnd_name like \"%{drug_name}%\" OR gnrc_name like \"%{drug_name}%\")"]

        if year:
            filters.append(f"year={year}")

        params = {
            "size": min(limit, 500),
            "filter": " AND ".join(filters),
        }

        try:
            result = await self._get(
                f"/{self.DATASET_PART_D_SPENDING}/data",
                params=params
            )

            spending_records = []
            data = result if isinstance(result, list) else result.get("data", [])

            for item in data:
                spending = PartDSpending(
                    brand_name=item.get("brnd_name", ""),
                    generic_name=item.get("gnrc_name"),
                    coverage_type=item.get("cvrg_type"),
                    year=self._safe_int(item.get("year")),
                    total_spending=self._safe_float(item.get("tot_spndng")),
                    total_spending_per_user=self._safe_float(item.get("tot_spndng_per_user")),
                    total_claims=self._safe_int(item.get("tot_clms")),
                    total_beneficiaries=self._safe_int(item.get("tot_benes")),
                    average_cost_per_unit=self._safe_float(item.get("avg_cst_per_unit")),
                    average_cost_per_claim=self._safe_float(item.get("avg_cst_per_clm")),
                    spending_change_pct=self._safe_float(item.get("chg_tot_spndng")),
                    cost_per_unit_change_pct=self._safe_float(item.get("chg_avg_cst_per_unit")),
                    beneficiary_change_pct=self._safe_float(item.get("chg_tot_benes")),
                    beneficiary_cost=self._safe_float(item.get("tot_bene_cst")),
                    beneficiary_cost_share_pct=self._safe_float(item.get("bene_cst_shr")),
                )
                spending_records.append(spending)

            return spending_records
        except Exception as e:
            logger.error(f"Error getting CMS Part D spending for '{drug_name}': {e}")
            return []

    async def get_spending_by_manufacturer(
        self,
        manufacturer_name: str,
        year: Optional[int] = None,
        limit: int = 100
    ) -> List[PartDSpending]:
        """
        Get Medicare Part D spending for all drugs from a manufacturer.

        Args:
            manufacturer_name: Manufacturer/labeler name
            year: Year of data
            limit: Maximum results

        Returns:
            List of Part D spending records
        """
        filters = [f"mftr_name like \"%{manufacturer_name}%\""]

        if year:
            filters.append(f"year={year}")

        params = {
            "size": min(limit, 500),
            "filter": " AND ".join(filters),
        }

        try:
            result = await self._get(
                f"/{self.DATASET_PART_D_SPENDING}/data",
                params=params
            )

            spending_records = []
            data = result if isinstance(result, list) else result.get("data", [])

            for item in data:
                spending = PartDSpending(
                    brand_name=item.get("brnd_name", ""),
                    generic_name=item.get("gnrc_name"),
                    coverage_type=item.get("cvrg_type"),
                    year=self._safe_int(item.get("year")),
                    total_spending=self._safe_float(item.get("tot_spndng")),
                    total_spending_per_user=self._safe_float(item.get("tot_spndng_per_user")),
                    total_claims=self._safe_int(item.get("tot_clms")),
                    total_beneficiaries=self._safe_int(item.get("tot_benes")),
                )
                spending_records.append(spending)

            return spending_records
        except Exception as e:
            logger.error(f"Error getting CMS spending for manufacturer '{manufacturer_name}': {e}")
            return []

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# Singleton instance
_cms_medicare_client: Optional[CMSMedicareClient] = None


async def get_cms_medicare_client(cache_manager: Optional[CacheManager] = None) -> CMSMedicareClient:
    """Get or create the CMS Medicare client instance."""
    global _cms_medicare_client

    if _cms_medicare_client is None:
        _cms_medicare_client = CMSMedicareClient(cache_manager)

    return _cms_medicare_client
