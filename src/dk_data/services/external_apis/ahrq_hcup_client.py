"""
AHRQ HCUP API Client.

Provides access to AHRQ HCUP (Healthcare Cost and Utilization Project) data:
- HCUPnet statistics (hospital inpatient stays, ED visits)
- Healthcare utilization by diagnosis
- Cost and charge data
- Length of stay statistics

API/Data Access: https://hcupnet.ahrq.gov/
Note: HCUP provides web-based tools; full datasets require licensing.
This client interfaces with publicly available HCUPnet summary statistics.

Rate Limit: Respectful usage recommended for web interface
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class HCUPStats:
    """HCUP statistics for a diagnosis/procedure."""

    # Diagnosis/Procedure identifiers
    code: str
    code_type: str  # ICD-10-CM, ICD-10-PCS, CCS, etc.
    description: Optional[str] = None

    # Setting
    setting: str = "inpatient"  # inpatient, ed, ambulatory

    # Time period
    year: Optional[int] = None

    # Volume metrics
    total_discharges: Optional[int] = None
    total_stays: Optional[int] = None  # Same as discharges for inpatient
    total_visits: Optional[int] = None  # For ED

    # Cost metrics (in USD)
    aggregate_charges: Optional[float] = None
    aggregate_costs: Optional[float] = None
    mean_charge: Optional[float] = None
    mean_cost: Optional[float] = None
    median_charge: Optional[float] = None
    median_cost: Optional[float] = None

    # Length of stay (for inpatient)
    mean_los: Optional[float] = None  # Days
    median_los: Optional[float] = None

    # Demographics
    percent_male: Optional[float] = None
    percent_female: Optional[float] = None
    mean_age: Optional[float] = None

    # Payer mix
    percent_medicare: Optional[float] = None
    percent_medicaid: Optional[float] = None
    percent_private: Optional[float] = None
    percent_uninsured: Optional[float] = None

    # Outcomes
    in_hospital_mortality_rate: Optional[float] = None
    readmission_rate_30_day: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "code_type": self.code_type,
            "description": self.description,
            "setting": self.setting,
            "year": self.year,
            "total_discharges": self.total_discharges,
            "total_stays": self.total_stays,
            "total_visits": self.total_visits,
            "aggregate_charges": self.aggregate_charges,
            "aggregate_costs": self.aggregate_costs,
            "mean_charge": self.mean_charge,
            "mean_cost": self.mean_cost,
            "median_charge": self.median_charge,
            "median_cost": self.median_cost,
            "mean_los": self.mean_los,
            "median_los": self.median_los,
            "percent_male": self.percent_male,
            "percent_female": self.percent_female,
            "mean_age": self.mean_age,
            "percent_medicare": self.percent_medicare,
            "percent_medicaid": self.percent_medicaid,
            "percent_private": self.percent_private,
            "percent_uninsured": self.percent_uninsured,
            "in_hospital_mortality_rate": self.in_hospital_mortality_rate,
            "readmission_rate_30_day": self.readmission_rate_30_day,
        }


@dataclass
class HospitalStayData:
    """Hospital inpatient stay data."""

    # Diagnosis
    principal_diagnosis_code: Optional[str] = None
    principal_diagnosis_desc: Optional[str] = None
    all_diagnosis_codes: List[str] = field(default_factory=list)

    # Procedure
    principal_procedure_code: Optional[str] = None
    principal_procedure_desc: Optional[str] = None

    # Time period
    year: Optional[int] = None

    # Volume
    number_of_stays: Optional[int] = None
    national_rate_per_100k: Optional[float] = None

    # Cost and charges
    aggregate_hospital_charges: Optional[float] = None
    aggregate_hospital_costs: Optional[float] = None
    mean_charges_per_stay: Optional[float] = None
    mean_cost_per_stay: Optional[float] = None

    # Length of stay
    mean_length_of_stay: Optional[float] = None
    median_length_of_stay: Optional[float] = None

    # Demographics breakdown
    stays_by_age_group: Dict[str, int] = field(default_factory=dict)
    stays_by_sex: Dict[str, int] = field(default_factory=dict)
    stays_by_payer: Dict[str, int] = field(default_factory=dict)
    stays_by_region: Dict[str, int] = field(default_factory=dict)

    # Outcomes
    in_hospital_deaths: Optional[int] = None
    in_hospital_mortality_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "principal_diagnosis_code": self.principal_diagnosis_code,
            "principal_diagnosis_desc": self.principal_diagnosis_desc,
            "all_diagnosis_codes": self.all_diagnosis_codes,
            "principal_procedure_code": self.principal_procedure_code,
            "principal_procedure_desc": self.principal_procedure_desc,
            "year": self.year,
            "number_of_stays": self.number_of_stays,
            "national_rate_per_100k": self.national_rate_per_100k,
            "aggregate_hospital_charges": self.aggregate_hospital_charges,
            "aggregate_hospital_costs": self.aggregate_hospital_costs,
            "mean_charges_per_stay": self.mean_charges_per_stay,
            "mean_cost_per_stay": self.mean_cost_per_stay,
            "mean_length_of_stay": self.mean_length_of_stay,
            "median_length_of_stay": self.median_length_of_stay,
            "stays_by_age_group": self.stays_by_age_group,
            "stays_by_sex": self.stays_by_sex,
            "stays_by_payer": self.stays_by_payer,
            "stays_by_region": self.stays_by_region,
            "in_hospital_deaths": self.in_hospital_deaths,
            "in_hospital_mortality_pct": self.in_hospital_mortality_pct,
        }


@dataclass
class EmergencyVisitData:
    """Emergency department visit data."""

    # Diagnosis
    diagnosis_code: Optional[str] = None
    diagnosis_desc: Optional[str] = None
    ccs_category: Optional[str] = None  # Clinical Classifications Software

    # Time period
    year: Optional[int] = None

    # Volume
    number_of_visits: Optional[int] = None
    national_rate_per_100k: Optional[float] = None

    # Disposition
    treat_and_release_count: Optional[int] = None
    admit_to_hospital_count: Optional[int] = None
    transfer_count: Optional[int] = None
    died_in_ed_count: Optional[int] = None

    # Percentages
    pct_treat_and_release: Optional[float] = None
    pct_admitted: Optional[float] = None

    # Cost
    mean_charge: Optional[float] = None
    median_charge: Optional[float] = None
    aggregate_charges: Optional[float] = None

    # Demographics
    visits_by_age_group: Dict[str, int] = field(default_factory=dict)
    visits_by_sex: Dict[str, int] = field(default_factory=dict)
    visits_by_payer: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnosis_code": self.diagnosis_code,
            "diagnosis_desc": self.diagnosis_desc,
            "ccs_category": self.ccs_category,
            "year": self.year,
            "number_of_visits": self.number_of_visits,
            "national_rate_per_100k": self.national_rate_per_100k,
            "treat_and_release_count": self.treat_and_release_count,
            "admit_to_hospital_count": self.admit_to_hospital_count,
            "transfer_count": self.transfer_count,
            "died_in_ed_count": self.died_in_ed_count,
            "pct_treat_and_release": self.pct_treat_and_release,
            "pct_admitted": self.pct_admitted,
            "mean_charge": self.mean_charge,
            "median_charge": self.median_charge,
            "aggregate_charges": self.aggregate_charges,
            "visits_by_age_group": self.visits_by_age_group,
            "visits_by_sex": self.visits_by_sex,
            "visits_by_payer": self.visits_by_payer,
        }


class AHRQHCUPClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for AHRQ HCUP (Healthcare Cost and Utilization Project) Data.

    HCUP is a family of healthcare databases and related software tools
    developed through a Federal-State-Industry partnership sponsored by AHRQ.

    This client provides access to publicly available statistics from HCUPnet,
    the online query system for HCUP data.

    Note: Full HCUP databases (NIS, NEDS, KID, etc.) require data use agreements.

    Usage:
        client = AHRQHCUPClient()
        stats = await client.get_hcup_stats(["K80"])  # Cholelithiasis
        stays = await client.get_hospital_stays("diabetes")
        ed_visits = await client.get_emergency_visits("chest pain")
    """

    # HCUPnet base URL
    BASE_URL = "https://hcupnet.ahrq.gov"

    # Common CCS (Clinical Classifications Software) categories
    CCS_CATEGORIES = {
        # Infectious diseases
        "1-9": "Infectious and parasitic diseases",

        # Neoplasms
        "11-45": "Neoplasms",
        "11": "Cancer of head and neck",
        "12": "Cancer of esophagus",
        "13": "Cancer of stomach",
        "14": "Cancer of colon",
        "19": "Cancer of bronchus/lung",
        "24": "Cancer of breast",

        # Endocrine/Metabolic
        "49-50": "Diabetes mellitus",
        "49": "Diabetes with complications",
        "50": "Diabetes without complications",

        # Cardiovascular
        "96-121": "Diseases of the circulatory system",
        "100": "Acute myocardial infarction",
        "101": "Coronary atherosclerosis",
        "108": "Congestive heart failure",
        "109": "Acute cerebrovascular disease",

        # Respiratory
        "122-134": "Diseases of the respiratory system",
        "122": "Pneumonia",
        "127": "Chronic obstructive pulmonary disease",
        "128": "Asthma",

        # Digestive
        "135-155": "Diseases of the digestive system",
        "149": "Biliary tract disease",

        # Musculoskeletal
        "203-212": "Diseases of the musculoskeletal system",
        "203": "Osteoarthritis",
        "205": "Spondylosis and related disorders",

        # Injuries
        "225-244": "Injury and poisoning",
        "226": "Fracture of neck of femur (hip)",

        # Mental health
        "650-670": "Mental illness",
        "657": "Mood disorders",
        "660": "Alcohol-related disorders",
        "661": "Substance-related disorders",
    }

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=60.0,
            max_retries=3,
            requests_per_second=0.5,  # Very conservative for web interface
            cache_ttl=2592000,  # 30 days - HCUP data updates annually
            headers={
                "Accept": "text/html,application/json",
                "User-Agent": "DataKinetic-TrialsPredictor/1.0 (Research Platform)",
            },
        )
        super().__init__(config, cache_manager)

        # Cache for pre-computed statistics (mock data for demonstration)
        self._stats_cache: Dict[str, HCUPStats] = {}

    async def health_check(self) -> bool:
        """Check if HCUPnet is accessible."""
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"AHRQ HCUP health check failed: {e}")
            return False

    async def get_hcup_stats(
        self,
        diagnosis_codes: List[str],
        year: Optional[int] = None,
        setting: str = "inpatient"
    ) -> List[HCUPStats]:
        """
        Get HCUP statistics for diagnosis codes.

        Args:
            diagnosis_codes: List of ICD-10-CM or CCS codes
            year: Data year (defaults to most recent available)
            setting: Care setting ("inpatient", "ed", "ambulatory")

        Returns:
            List of HCUP statistics
        """
        if year is None:
            year = 2021  # Most recent commonly available year

        stats_list = []

        for code in diagnosis_codes:
            # Check if we have pre-computed stats
            cache_key = f"{code}_{year}_{setting}"

            if cache_key in self._stats_cache:
                stats_list.append(self._stats_cache[cache_key])
                continue

            # Get stats for this code
            stats = await self._get_stats_for_code(code, year, setting)
            if stats:
                self._stats_cache[cache_key] = stats
                stats_list.append(stats)

        return stats_list

    async def get_hospital_stays(
        self,
        condition: str,
        year: Optional[int] = None,
        state: Optional[str] = None
    ) -> List[HospitalStayData]:
        """
        Get hospital inpatient stay data for a condition.

        Args:
            condition: Condition name or code
            year: Data year
            state: State filter (optional)

        Returns:
            List of hospital stay data
        """
        if year is None:
            year = 2021

        # Map common condition names to CCS categories
        ccs_code = self._map_condition_to_ccs(condition)

        if not ccs_code:
            # If no mapping, search by name
            ccs_code = condition

        try:
            # Get data from HCUPnet (via web interface or API)
            stay_data = await self._query_inpatient_data(ccs_code, year, state)
            return stay_data
        except Exception as e:
            logger.error(f"Error getting hospital stay data for '{condition}': {e}")
            return []

    async def get_emergency_visits(
        self,
        condition: str,
        year: Optional[int] = None,
        state: Optional[str] = None
    ) -> List[EmergencyVisitData]:
        """
        Get emergency department visit data for a condition.

        Args:
            condition: Condition name or code
            year: Data year
            state: State filter (optional)

        Returns:
            List of ED visit data
        """
        if year is None:
            year = 2021

        ccs_code = self._map_condition_to_ccs(condition)

        if not ccs_code:
            ccs_code = condition

        try:
            ed_data = await self._query_ed_data(ccs_code, year, state)
            return ed_data
        except Exception as e:
            logger.error(f"Error getting ED visit data for '{condition}': {e}")
            return []

    async def get_trending_conditions(
        self,
        setting: str = "inpatient",
        year_range: Optional[Tuple[int, int]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get trending conditions by utilization.

        Args:
            setting: Care setting
            year_range: Years to analyze
            limit: Maximum results

        Returns:
            List of conditions with trend data
        """
        if year_range is None:
            year_range = (2018, 2021)

        # This would query HCUPnet for top conditions
        # For now, return known high-volume conditions
        high_volume_conditions = [
            {"code": "108", "name": "Congestive heart failure", "trend": "stable"},
            {"code": "100", "name": "Acute myocardial infarction", "trend": "decreasing"},
            {"code": "122", "name": "Pneumonia", "trend": "variable"},
            {"code": "127", "name": "COPD", "trend": "stable"},
            {"code": "149", "name": "Biliary tract disease", "trend": "increasing"},
            {"code": "203", "name": "Osteoarthritis", "trend": "increasing"},
            {"code": "226", "name": "Hip fracture", "trend": "stable"},
            {"code": "49", "name": "Diabetes with complications", "trend": "increasing"},
            {"code": "109", "name": "Acute cerebrovascular disease", "trend": "stable"},
            {"code": "128", "name": "Asthma", "trend": "decreasing"},
        ]

        return high_volume_conditions[:limit]

    async def _get_stats_for_code(
        self,
        code: str,
        year: int,
        setting: str
    ) -> Optional[HCUPStats]:
        """Get HCUP stats for a single code."""
        # Determine code type
        code_type = self._determine_code_type(code)

        # Get description
        description = self._get_code_description(code, code_type)

        # Query HCUPnet for stats
        # In production, this would make actual queries to HCUPnet
        # For now, return structure with available data

        try:
            # Build HCUPnet query URL
            query_url = self._build_hcupnet_query_url(code, year, setting)

            client = await self._get_client()
            await self._rate_limiter.acquire()

            response = await client.get(query_url)

            if response.status_code != 200:
                return None

            # Parse response
            return self._parse_hcupnet_response(response.text, code, code_type, year, setting, description)

        except Exception as e:
            logger.warning(f"Could not retrieve HCUP stats for {code}: {e}")

            # Return basic stats structure
            return HCUPStats(
                code=code,
                code_type=code_type,
                description=description,
                setting=setting,
                year=year,
            )

    async def _query_inpatient_data(
        self,
        ccs_code: str,
        year: int,
        state: Optional[str]
    ) -> List[HospitalStayData]:
        """Query HCUPnet for inpatient data."""
        # Build query and execute
        # In production, this would interface with HCUPnet

        try:
            # Placeholder response structure
            stay = HospitalStayData(
                principal_diagnosis_code=ccs_code,
                principal_diagnosis_desc=self.CCS_CATEGORIES.get(ccs_code, ccs_code),
                year=year,
            )

            return [stay]
        except Exception as e:
            logger.error(f"Error querying inpatient data: {e}")
            return []

    async def _query_ed_data(
        self,
        ccs_code: str,
        year: int,
        state: Optional[str]
    ) -> List[EmergencyVisitData]:
        """Query HCUPnet for ED visit data."""
        try:
            visit = EmergencyVisitData(
                diagnosis_code=ccs_code,
                diagnosis_desc=self.CCS_CATEGORIES.get(ccs_code, ccs_code),
                ccs_category=ccs_code,
                year=year,
            )

            return [visit]
        except Exception as e:
            logger.error(f"Error querying ED data: {e}")
            return []

    def _map_condition_to_ccs(self, condition: str) -> Optional[str]:
        """Map condition name to CCS code."""
        condition_lower = condition.lower()

        # Common condition mappings
        mappings = {
            "heart failure": "108",
            "chf": "108",
            "congestive heart failure": "108",
            "heart attack": "100",
            "myocardial infarction": "100",
            "ami": "100",
            "stroke": "109",
            "cerebrovascular": "109",
            "pneumonia": "122",
            "copd": "127",
            "chronic obstructive pulmonary": "127",
            "asthma": "128",
            "diabetes": "49",
            "diabetic": "49",
            "hip fracture": "226",
            "osteoarthritis": "203",
            "arthritis": "203",
            "gallbladder": "149",
            "biliary": "149",
            "cholecystitis": "149",
            "lung cancer": "19",
            "breast cancer": "24",
            "colon cancer": "14",
            "depression": "657",
            "mood disorder": "657",
            "alcohol": "660",
            "substance abuse": "661",
            "opioid": "661",
            "chest pain": "102",
            "sepsis": "2",
            "septicemia": "2",
        }

        for key, ccs in mappings.items():
            if key in condition_lower:
                return ccs

        return None

    def _determine_code_type(self, code: str) -> str:
        """Determine the type of code (ICD-10, CCS, etc.)."""
        # ICD-10-CM codes typically start with letter and have 3-7 characters
        if re.match(r'^[A-Z]\d{2}', code):
            return "ICD-10-CM"

        # ICD-10-PCS codes are 7 alphanumeric characters
        if re.match(r'^[0-9A-Z]{7}$', code):
            return "ICD-10-PCS"

        # CCS codes are numeric, typically 1-3 digits
        if re.match(r'^\d{1,3}$', code):
            return "CCS"

        # CCS category ranges
        if re.match(r'^\d{1,3}-\d{1,3}$', code):
            return "CCS-RANGE"

        return "UNKNOWN"

    def _get_code_description(
        self,
        code: str,
        code_type: str
    ) -> Optional[str]:
        """Get description for a code."""
        if code_type in ["CCS", "CCS-RANGE"]:
            return self.CCS_CATEGORIES.get(code)

        # For ICD-10, would look up in code database
        return None

    def _build_hcupnet_query_url(
        self,
        code: str,
        year: int,
        setting: str
    ) -> str:
        """Build HCUPnet query URL."""
        # HCUPnet uses complex URL parameters
        # This is a simplified version
        base_path = "/HCUPnet.jsp"

        # Map setting to HCUPnet database
        db_map = {
            "inpatient": "NIS",  # National Inpatient Sample
            "ed": "NEDS",       # Nationwide Emergency Department Sample
            "ambulatory": "SASD", # State Ambulatory Surgery Databases
        }

        db = db_map.get(setting, "NIS")

        return f"{base_path}?Id=&Form=&JS=N&Action=%3E%3ENext%3E%3E&_SUMMARY=S&_TYPE=C&Tefession=1&_YEAR={year}&_DATABASE={db}&_CCS={code}"

    def _parse_hcupnet_response(
        self,
        html: str,
        code: str,
        code_type: str,
        year: int,
        setting: str,
        description: Optional[str]
    ) -> HCUPStats:
        """Parse HCUPnet HTML response into HCUPStats."""
        stats = HCUPStats(
            code=code,
            code_type=code_type,
            description=description,
            setting=setting,
            year=year,
        )

        # Parse statistics from HTML tables
        # HCUPnet returns data in HTML tables

        # Look for total discharges/visits
        discharges_match = re.search(
            r'(?:Total|Number of).*?(?:discharges|stays|visits).*?</td>\s*<td[^>]*>([0-9,]+)',
            html, re.IGNORECASE | re.DOTALL
        )
        if discharges_match:
            stats.total_discharges = self._parse_number(discharges_match.group(1))
            stats.total_stays = stats.total_discharges

        # Look for mean length of stay
        los_match = re.search(
            r'Mean LOS.*?</td>\s*<td[^>]*>([0-9.]+)',
            html, re.IGNORECASE | re.DOTALL
        )
        if los_match:
            stats.mean_los = self._safe_float(los_match.group(1))

        # Look for mean charges
        charges_match = re.search(
            r'Mean.*?charge.*?</td>\s*<td[^>]*>\$?([0-9,]+)',
            html, re.IGNORECASE | re.DOTALL
        )
        if charges_match:
            stats.mean_charge = self._parse_number(charges_match.group(1))

        # Look for mean cost
        cost_match = re.search(
            r'Mean.*?cost.*?</td>\s*<td[^>]*>\$?([0-9,]+)',
            html, re.IGNORECASE | re.DOTALL
        )
        if cost_match:
            stats.mean_cost = self._parse_number(cost_match.group(1))

        # Look for mortality rate
        mortality_match = re.search(
            r'(?:In-hospital|Hospital).*?mortality.*?</td>\s*<td[^>]*>([0-9.]+)%?',
            html, re.IGNORECASE | re.DOTALL
        )
        if mortality_match:
            stats.in_hospital_mortality_rate = self._safe_float(mortality_match.group(1))

        return stats

    def _parse_number(self, value: str) -> Optional[int]:
        """Parse a number string with commas."""
        if not value:
            return None
        try:
            return int(value.replace(',', '').replace('$', ''))
        except ValueError:
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('$', '').replace('%', '')
            return float(value)
        except (ValueError, TypeError):
            return None


# Singleton instance
_ahrq_hcup_client: Optional[AHRQHCUPClient] = None


async def get_ahrq_hcup_client(cache_manager: Optional[CacheManager] = None) -> AHRQHCUPClient:
    """Get or create the AHRQ HCUP client instance."""
    global _ahrq_hcup_client

    if _ahrq_hcup_client is None:
        _ahrq_hcup_client = AHRQHCUPClient(cache_manager)

    return _ahrq_hcup_client
