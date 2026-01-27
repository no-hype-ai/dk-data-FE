"""
CDC WONDER API Client.

Provides access to CDC WONDER (Wide-ranging Online Data for Epidemiologic Research):
- Mortality data (underlying and multiple causes of death)
- Natality data (birth statistics)
- Population estimates
- Cause of death statistics

API Documentation: https://wonder.cdc.gov/wonder/help/WONDER-API.html
Note: CDC WONDER requires agreed terms of use. Some datasets require special access.

Rate Limit: Respectful usage recommended (no official limit)
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager, DataSource


@dataclass
class MortalityData:
    """CDC WONDER mortality data record."""

    # Geographic
    state: Optional[str] = None
    state_code: Optional[str] = None
    county: Optional[str] = None
    county_code: Optional[str] = None

    # Time period
    year: Optional[int] = None
    month: Optional[int] = None

    # Demographics
    age_group: Optional[str] = None
    gender: Optional[str] = None
    race: Optional[str] = None
    hispanic_origin: Optional[str] = None

    # Cause of death
    icd10_code: Optional[str] = None
    icd10_description: Optional[str] = None
    underlying_cause: Optional[str] = None

    # Metrics
    deaths: Optional[int] = None
    population: Optional[int] = None
    crude_rate: Optional[float] = None
    age_adjusted_rate: Optional[float] = None

    # Standard errors/confidence intervals
    crude_rate_se: Optional[float] = None
    age_adjusted_rate_se: Optional[float] = None
    crude_rate_ci_lower: Optional[float] = None
    crude_rate_ci_upper: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "state_code": self.state_code,
            "county": self.county,
            "county_code": self.county_code,
            "year": self.year,
            "month": self.month,
            "age_group": self.age_group,
            "gender": self.gender,
            "race": self.race,
            "hispanic_origin": self.hispanic_origin,
            "icd10_code": self.icd10_code,
            "icd10_description": self.icd10_description,
            "underlying_cause": self.underlying_cause,
            "deaths": self.deaths,
            "population": self.population,
            "crude_rate": self.crude_rate,
            "age_adjusted_rate": self.age_adjusted_rate,
            "crude_rate_se": self.crude_rate_se,
            "age_adjusted_rate_se": self.age_adjusted_rate_se,
            "crude_rate_ci_lower": self.crude_rate_ci_lower,
            "crude_rate_ci_upper": self.crude_rate_ci_upper,
        }


@dataclass
class NatalityData:
    """CDC WONDER natality (birth) data record."""

    # Geographic
    state: Optional[str] = None
    state_code: Optional[str] = None
    county: Optional[str] = None

    # Time period
    year: Optional[int] = None

    # Mother demographics
    mother_age_group: Optional[str] = None
    mother_race: Optional[str] = None
    mother_education: Optional[str] = None

    # Birth characteristics
    birth_weight_group: Optional[str] = None
    gestational_age_group: Optional[str] = None
    plurality: Optional[str] = None  # Single, Twin, etc.

    # Health conditions
    congenital_anomalies: List[str] = field(default_factory=list)
    maternal_conditions: List[str] = field(default_factory=list)

    # Metrics
    births: Optional[int] = None
    birth_rate: Optional[float] = None
    low_birth_weight_pct: Optional[float] = None
    preterm_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "state_code": self.state_code,
            "county": self.county,
            "year": self.year,
            "mother_age_group": self.mother_age_group,
            "mother_race": self.mother_race,
            "mother_education": self.mother_education,
            "birth_weight_group": self.birth_weight_group,
            "gestational_age_group": self.gestational_age_group,
            "plurality": self.plurality,
            "congenital_anomalies": self.congenital_anomalies,
            "maternal_conditions": self.maternal_conditions,
            "births": self.births,
            "birth_rate": self.birth_rate,
            "low_birth_weight_pct": self.low_birth_weight_pct,
            "preterm_pct": self.preterm_pct,
        }


@dataclass
class CauseOfDeathStats:
    """Aggregated cause of death statistics."""

    cause_code: str
    cause_name: str

    # Total metrics
    total_deaths: Optional[int] = None

    # Rates
    crude_rate: Optional[float] = None  # Per 100,000
    age_adjusted_rate: Optional[float] = None  # Per 100,000

    # Rankings
    rank_all_causes: Optional[int] = None
    percent_of_total: Optional[float] = None

    # Time trends
    year_range: Optional[Tuple[int, int]] = None
    rate_change_pct: Optional[float] = None  # Change over period

    # By demographics
    rate_by_age: Dict[str, float] = field(default_factory=dict)
    rate_by_gender: Dict[str, float] = field(default_factory=dict)
    rate_by_race: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cause_code": self.cause_code,
            "cause_name": self.cause_name,
            "total_deaths": self.total_deaths,
            "crude_rate": self.crude_rate,
            "age_adjusted_rate": self.age_adjusted_rate,
            "rank_all_causes": self.rank_all_causes,
            "percent_of_total": self.percent_of_total,
            "year_range": list(self.year_range) if self.year_range else None,
            "rate_change_pct": self.rate_change_pct,
            "rate_by_age": self.rate_by_age,
            "rate_by_gender": self.rate_by_gender,
            "rate_by_race": self.rate_by_race,
        }


class CDCWonderClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for CDC WONDER Public Health Data.

    CDC WONDER provides access to a wide array of public health datasets.
    Note: Some datasets have special access requirements.

    The API uses XML-based requests and responses.

    Usage:
        client = CDCWonderClient()
        mortality = await client.query_mortality(["C34"], year_range=(2018, 2022))
        stats = await client.get_cause_of_death_stats("C34")  # Lung cancer
    """

    # CDC WONDER base URL
    BASE_URL = "https://wonder.cdc.gov"

    # Database identifiers
    # D76 = Underlying Cause of Death, 1999-2020
    # D77 = Multiple Cause of Death, 1999-2020
    # D66 = Natality, 2007-2022
    DB_MORTALITY_UNDERLYING = "D76"
    DB_MORTALITY_MULTIPLE = "D77"
    DB_NATALITY = "D66"

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=120.0,  # WONDER queries can be very slow
            max_retries=3,
            requests_per_second=0.5,  # Very conservative rate limit
            cache_ttl=2592000,  # 30 days - CDC data updates annually
            headers={
                "Content-Type": "application/xml",
                "Accept": "application/xml",
            },
        )
        super().__init__(config, cache_manager)

    async def health_check(self) -> bool:
        """Check if CDC WONDER is accessible."""
        try:
            client = await self._get_client()
            response = await client.get("/ucd-icd10.html")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"CDC WONDER health check failed: {e}")
            return False

    async def query_mortality(
        self,
        icd10_codes: List[str],
        year_range: Optional[Tuple[int, int]] = None,
        states: Optional[List[str]] = None,
        age_groups: Optional[List[str]] = None,
        genders: Optional[List[str]] = None,
        group_by: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[MortalityData]:
        """
        Query mortality data from CDC WONDER.

        Args:
            icd10_codes: List of ICD-10 codes to query (e.g., ["C34"] for lung cancer)
            year_range: Tuple of (start_year, end_year)
            states: List of state FIPS codes or abbreviations
            age_groups: Age group filters
            genders: Gender filters ("M", "F")
            group_by: Fields to group by (year, state, age, gender, race)
            limit: Maximum results

        Returns:
            List of mortality data records
        """
        # Build request XML
        request_xml = self._build_mortality_request(
            icd10_codes=icd10_codes,
            year_range=year_range,
            states=states,
            age_groups=age_groups,
            genders=genders,
            group_by=group_by or ["year"],
        )

        try:
            # CDC WONDER uses POST with XML
            client = await self._get_client()

            # Rate limiting
            await self._rate_limiter.acquire()

            response = await client.post(
                f"/controller/datarequest/{self.DB_MORTALITY_UNDERLYING}",
                content=request_xml,
                headers={"Content-Type": "application/xml"},
            )

            if response.status_code != 200:
                logger.error(f"CDC WONDER query failed with status {response.status_code}")
                return []

            # Parse response
            results = self._parse_mortality_response(response.text)
            return results[:limit]
        except Exception as e:
            logger.error(f"Error querying CDC WONDER mortality data: {e}")
            return []

    async def query_natality(
        self,
        conditions: Optional[List[str]] = None,
        year_range: Optional[Tuple[int, int]] = None,
        states: Optional[List[str]] = None,
        group_by: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[NatalityData]:
        """
        Query natality (birth) data from CDC WONDER.

        Args:
            conditions: Maternal or infant conditions to filter
            year_range: Tuple of (start_year, end_year)
            states: List of state FIPS codes
            group_by: Fields to group by
            limit: Maximum results

        Returns:
            List of natality data records
        """
        # Build request XML
        request_xml = self._build_natality_request(
            conditions=conditions,
            year_range=year_range,
            states=states,
            group_by=group_by or ["year"],
        )

        try:
            client = await self._get_client()

            await self._rate_limiter.acquire()

            response = await client.post(
                f"/controller/datarequest/{self.DB_NATALITY}",
                content=request_xml,
                headers={"Content-Type": "application/xml"},
            )

            if response.status_code != 200:
                logger.error(f"CDC WONDER natality query failed with status {response.status_code}")
                return []

            results = self._parse_natality_response(response.text)
            return results[:limit]
        except Exception as e:
            logger.error(f"Error querying CDC WONDER natality data: {e}")
            return []

    async def get_cause_of_death_stats(
        self,
        cause_code: str,
        year_range: Optional[Tuple[int, int]] = None
    ) -> Optional[CauseOfDeathStats]:
        """
        Get aggregated statistics for a specific cause of death.

        Args:
            cause_code: ICD-10 cause of death code (e.g., "C34" for lung cancer)
            year_range: Years to analyze

        Returns:
            CauseOfDeathStats or None if no data
        """
        if year_range is None:
            year_range = (2018, 2022)

        # Query overall mortality for this cause
        mortality_data = await self.query_mortality(
            icd10_codes=[cause_code],
            year_range=year_range,
            group_by=["year"],
        )

        if not mortality_data:
            return None

        # Aggregate statistics
        total_deaths = sum(m.deaths or 0 for m in mortality_data)

        # Calculate average rate
        rates = [m.age_adjusted_rate for m in mortality_data if m.age_adjusted_rate]
        avg_rate = sum(rates) / len(rates) if rates else None

        # Get cause name from first result
        cause_name = mortality_data[0].icd10_description if mortality_data else cause_code

        # Query by demographics for breakdown
        rate_by_gender = {}
        rate_by_age = {}

        # Query by gender
        gender_data = await self.query_mortality(
            icd10_codes=[cause_code],
            year_range=year_range,
            group_by=["gender"],
        )
        for record in gender_data:
            if record.gender and record.age_adjusted_rate:
                rate_by_gender[record.gender] = record.age_adjusted_rate

        # Query by age
        age_data = await self.query_mortality(
            icd10_codes=[cause_code],
            year_range=year_range,
            group_by=["age"],
        )
        for record in age_data:
            if record.age_group and record.crude_rate:
                rate_by_age[record.age_group] = record.crude_rate

        return CauseOfDeathStats(
            cause_code=cause_code,
            cause_name=cause_name or cause_code,
            total_deaths=total_deaths,
            age_adjusted_rate=avg_rate,
            year_range=year_range,
            rate_by_gender=rate_by_gender,
            rate_by_age=rate_by_age,
        )

    async def get_icd10_mortality_codes(
        self,
        category: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get list of ICD-10 codes and their descriptions for mortality queries.

        Args:
            category: Filter by category (C=Cancer, I=Circulatory, J=Respiratory, etc.)

        Returns:
            Dictionary of code -> description
        """
        # Common mortality ICD-10 codes
        # This is a curated list; full list would come from CDC
        codes = {
            # Neoplasms (Cancer)
            "C00-C97": "Malignant neoplasms",
            "C18-C21": "Malignant neoplasm of colon, rectum and anus",
            "C22": "Malignant neoplasm of liver and intrahepatic bile ducts",
            "C25": "Malignant neoplasm of pancreas",
            "C33-C34": "Malignant neoplasm of trachea, bronchus and lung",
            "C34": "Malignant neoplasm of bronchus and lung",
            "C43": "Malignant melanoma of skin",
            "C50": "Malignant neoplasm of breast",
            "C61": "Malignant neoplasm of prostate",
            "C67": "Malignant neoplasm of bladder",
            "C71": "Malignant neoplasm of brain",
            "C91-C95": "Leukemia",

            # Circulatory diseases
            "I00-I99": "Diseases of the circulatory system",
            "I10-I15": "Hypertensive diseases",
            "I20-I25": "Ischemic heart diseases",
            "I21": "Acute myocardial infarction",
            "I60-I69": "Cerebrovascular diseases",
            "I50": "Heart failure",

            # Respiratory diseases
            "J00-J99": "Diseases of the respiratory system",
            "J09-J18": "Influenza and pneumonia",
            "J40-J47": "Chronic lower respiratory diseases",
            "J44": "Chronic obstructive pulmonary disease",

            # Metabolic diseases
            "E10-E14": "Diabetes mellitus",
            "E11": "Type 2 diabetes mellitus",

            # Neurological diseases
            "G30": "Alzheimer disease",
            "G20": "Parkinson disease",

            # External causes
            "V01-Y89": "External causes of morbidity and mortality",
            "X60-X84": "Intentional self-harm (suicide)",
            "X85-Y09": "Assault (homicide)",
        }

        if category:
            return {k: v for k, v in codes.items() if k.startswith(category)}

        return codes

    def _build_mortality_request(
        self,
        icd10_codes: List[str],
        year_range: Optional[Tuple[int, int]] = None,
        states: Optional[List[str]] = None,
        age_groups: Optional[List[str]] = None,
        genders: Optional[List[str]] = None,
        group_by: Optional[List[str]] = None,
    ) -> str:
        """Build XML request for mortality query."""
        # CDC WONDER uses a specific XML format
        # This is a simplified version
        params = []

        # ICD-10 codes
        for code in icd10_codes:
            params.append(f'<parameter><name>F_D76.V2</name><value>{code}</value></parameter>')

        # Years
        if year_range:
            for year in range(year_range[0], year_range[1] + 1):
                params.append(f'<parameter><name>F_D76.V1</name><value>{year}</value></parameter>')

        # States
        if states:
            for state in states:
                params.append(f'<parameter><name>F_D76.V9</name><value>{state}</value></parameter>')

        # Gender
        if genders:
            for gender in genders:
                params.append(f'<parameter><name>F_D76.V7</name><value>{gender}</value></parameter>')

        # Group by
        group_codes = {
            "year": "D76.V1",
            "state": "D76.V9",
            "age": "D76.V5",
            "gender": "D76.V7",
            "race": "D76.V8",
            "cause": "D76.V2",
        }

        if group_by:
            for gb in group_by:
                if gb in group_codes:
                    params.append(f'<parameter><name>B_{group_codes[gb]}</name><value>*All*</value></parameter>')

        # Measures to return
        params.append('<parameter><name>M_1</name><value>D76.M1</value></parameter>')  # Deaths
        params.append('<parameter><name>M_2</name><value>D76.M2</value></parameter>')  # Population
        params.append('<parameter><name>M_3</name><value>D76.M3</value></parameter>')  # Crude Rate

        # Agree to terms of data use (required)
        params.append('<parameter><name>accept_datause_restrictions</name><value>true</value></parameter>')

        return f'<?xml version="1.0" encoding="utf-8"?><request-parameters>{"".join(params)}</request-parameters>'

    def _build_natality_request(
        self,
        conditions: Optional[List[str]] = None,
        year_range: Optional[Tuple[int, int]] = None,
        states: Optional[List[str]] = None,
        group_by: Optional[List[str]] = None,
    ) -> str:
        """Build XML request for natality query."""
        params = []

        # Years
        if year_range:
            for year in range(year_range[0], year_range[1] + 1):
                params.append(f'<parameter><name>F_D66.V1</name><value>{year}</value></parameter>')

        # States
        if states:
            for state in states:
                params.append(f'<parameter><name>F_D66.V9</name><value>{state}</value></parameter>')

        # Group by
        group_codes = {
            "year": "D66.V1",
            "state": "D66.V9",
            "mother_age": "D66.V2",
            "mother_race": "D66.V3",
        }

        if group_by:
            for gb in group_by:
                if gb in group_codes:
                    params.append(f'<parameter><name>B_{group_codes[gb]}</name><value>*All*</value></parameter>')

        # Measures
        params.append('<parameter><name>M_1</name><value>D66.M1</value></parameter>')  # Births

        # Terms
        params.append('<parameter><name>accept_datause_restrictions</name><value>true</value></parameter>')

        return f'<?xml version="1.0" encoding="utf-8"?><request-parameters>{"".join(params)}</request-parameters>'

    def _parse_mortality_response(self, xml_text: str) -> List[MortalityData]:
        """Parse XML response from mortality query."""
        results = []

        try:
            root = ET.fromstring(xml_text)

            # Find data rows
            for row in root.findall('.//r'):
                data = MortalityData()

                # Parse columns based on structure
                cols = row.findall('c')
                for i, col in enumerate(cols):
                    value = col.text or col.get('v', '')
                    label = col.get('l', '')

                    # Map columns to fields based on label or position
                    if 'Year' in label:
                        data.year = self._safe_int(value)
                    elif 'State' in label:
                        data.state = value
                    elif 'Age' in label:
                        data.age_group = value
                    elif 'Gender' in label:
                        data.gender = value
                    elif 'Race' in label:
                        data.race = value
                    elif 'ICD' in label or 'Cause' in label:
                        data.icd10_code = value
                        data.icd10_description = label
                    elif 'Deaths' in label:
                        data.deaths = self._safe_int(value)
                    elif 'Population' in label:
                        data.population = self._safe_int(value)
                    elif 'Crude Rate' in label:
                        data.crude_rate = self._safe_float(value)
                    elif 'Age Adjusted' in label:
                        data.age_adjusted_rate = self._safe_float(value)

                if data.deaths is not None or data.crude_rate is not None:
                    results.append(data)

        except ET.ParseError as e:
            logger.error(f"Error parsing CDC WONDER XML: {e}")

        return results

    def _parse_natality_response(self, xml_text: str) -> List[NatalityData]:
        """Parse XML response from natality query."""
        results = []

        try:
            root = ET.fromstring(xml_text)

            for row in root.findall('.//r'):
                data = NatalityData()

                cols = row.findall('c')
                for col in cols:
                    value = col.text or col.get('v', '')
                    label = col.get('l', '')

                    if 'Year' in label:
                        data.year = self._safe_int(value)
                    elif 'State' in label:
                        data.state = value
                    elif 'Mother' in label and 'Age' in label:
                        data.mother_age_group = value
                    elif 'Mother' in label and 'Race' in label:
                        data.mother_race = value
                    elif 'Births' in label:
                        data.births = self._safe_int(value)
                    elif 'Birth Rate' in label:
                        data.birth_rate = self._safe_float(value)

                if data.births is not None:
                    results.append(data)

        except ET.ParseError as e:
            logger.error(f"Error parsing CDC WONDER natality XML: {e}")

        return results

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to int."""
        if value is None or value == '' or value == 'Suppressed' or value == 'Unreliable':
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == '' or value == 'Suppressed' or value == 'Unreliable':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# Singleton instance
_cdc_wonder_client: Optional[CDCWonderClient] = None


async def get_cdc_wonder_client(cache_manager: Optional[CacheManager] = None) -> CDCWonderClient:
    """Get or create the CDC WONDER client instance."""
    global _cdc_wonder_client

    if _cdc_wonder_client is None:
        _cdc_wonder_client = CDCWonderClient(cache_manager)

    return _cdc_wonder_client
