"""
Health Canada Drug Product Database (DPD) Client.

Implements T131: HealthCanadaClient class for accessing Canadian drug data.

Data sources:
- Health Canada Drug Product Database: https://www.canada.ca/en/health-canada/services/drugs-health-products/drug-products/drug-product-database.html
- DPD API: https://health-products.canada.ca/api/drug/
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
import aiohttp
from loguru import logger

from .base_client import BaseAPIClient, APIClientConfig


class HealthCanadaClass(str, Enum):
    """Health Canada drug classification."""
    HUMAN = "Human"
    VETERINARY = "Veterinary"
    DISINFECTANT = "Disinfectant"


class HealthCanadaStatus(str, Enum):
    """Health Canada authorization status."""
    MARKETED = "Marketed"
    APPROVED = "Approved"
    CANCELLED_POST = "Cancelled Post Market"
    CANCELLED_PRE = "Cancelled Pre Market"
    DORMANT = "Dormant"


class HealthCanadaSchedule(str, Enum):
    """Drug scheduling in Canada."""
    PRESCRIPTION = "Prescription"
    SCHEDULE_D = "Schedule D"  # Biologics
    OTC = "OTC"
    UNSCHEDULED = "Unscheduled"


@dataclass
class HealthCanadaProduct:
    """Health Canada drug product information."""
    drug_identification_number: str  # DIN
    brand_name: str
    company_name: str
    drug_class: HealthCanadaClass
    status: HealthCanadaStatus
    active_ingredients: List[Dict[str, str]] = field(default_factory=list)
    schedule: Optional[HealthCanadaSchedule] = None
    atc_code: Optional[str] = None
    route_of_administration: Optional[str] = None
    dosage_form: Optional[str] = None
    first_market_date: Optional[date] = None
    last_update_date: Optional[date] = None
    therapeutic_class: Optional[str] = None
    ai_group_number: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "din": self.drug_identification_number,
            "brand_name": self.brand_name,
            "company_name": self.company_name,
            "drug_class": self.drug_class.value,
            "status": self.status.value,
            "active_ingredients": self.active_ingredients,
            "schedule": self.schedule.value if self.schedule else None,
            "atc_code": self.atc_code,
            "route_of_administration": self.route_of_administration,
            "dosage_form": self.dosage_form,
            "first_market_date": self.first_market_date.isoformat() if self.first_market_date else None,
            "therapeutic_class": self.therapeutic_class,
        }


@dataclass
class HealthCanadaAdverseReaction:
    """Health Canada adverse reaction report."""
    report_id: str
    report_date: date
    drug_name: str
    reaction_name: str
    seriousness: str
    outcome: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None


class HealthCanadaClient(BaseAPIClient):
    """
    Client for Health Canada Drug Product Database (DPD) API.

    API Documentation:
    https://health-products.canada.ca/api/documentation/dpd-documentation-en.html
    """

    BASE_URL = "https://health-products.canada.ca/api/drug"

    # API endpoints
    ENDPOINTS = {
        "drug_product": "/drugproduct",
        "active_ingredient": "/activeingredient",
        "company": "/company",
        "status": "/status",
        "schedule": "/schedule",
        "route": "/route",
        "form": "/form",
        "therapeutic_class": "/therapeuticclass",
    }

    def __init__(self, cache_ttl: int = 86400):
        config = APIClientConfig(
            base_url=self.BASE_URL,
            requests_per_second=2.0,  # 2 requests per second (conservative)
            cache_ttl=cache_ttl,
        )
        super().__init__(config)

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        status: Optional[HealthCanadaStatus] = None,
    ) -> List[HealthCanadaProduct]:
        """
        Search for Health Canada authorized products.

        Args:
            query: Brand name or active ingredient to search
            limit: Maximum number of results
            status: Filter by status (optional)

        Returns:
            List of matching products
        """
        logger.debug(f"Searching Health Canada DPD for: {query}")

        products = []

        try:
            # Search by brand name
            brand_results = await self._search_by_brand(query)
            products.extend(brand_results)

            # Search by active ingredient
            ingredient_results = await self._search_by_ingredient(query)

            # Deduplicate by DIN
            seen_dins = {p.drug_identification_number for p in products}
            for p in ingredient_results:
                if p.drug_identification_number not in seen_dins:
                    products.append(p)
                    seen_dins.add(p.drug_identification_number)

            # Filter by status if specified
            if status:
                products = [p for p in products if p.status == status]

            return products[:limit]

        except Exception as e:
            logger.error(f"Error searching Health Canada DPD: {e}")
            return []

    async def _search_by_brand(self, brand_name: str) -> List[HealthCanadaProduct]:
        """Search products by brand name."""
        try:
            params = {"brandname": brand_name}
            response = await self._make_request(
                f"{self.ENDPOINTS['drug_product']}",
                params=params,
            )

            if not response:
                return []

            return [self._parse_product(item) for item in response if item]

        except Exception as e:
            logger.warning(f"Brand name search failed: {e}")
            return []

    async def _search_by_ingredient(self, ingredient: str) -> List[HealthCanadaProduct]:
        """Search products by active ingredient."""
        try:
            params = {"ingredient": ingredient}
            response = await self._make_request(
                f"{self.ENDPOINTS['active_ingredient']}",
                params=params,
            )

            if not response:
                return []

            # Get unique drug codes
            drug_codes = list(set(item.get("drug_code") for item in response if item.get("drug_code")))

            # Fetch full product info for each drug code
            products = []
            for code in drug_codes[:20]:  # Limit to prevent too many requests
                product = await self.get_product_by_code(code)
                if product:
                    products.append(product)

            return products

        except Exception as e:
            logger.warning(f"Ingredient search failed: {e}")
            return []

    async def get_product_by_din(self, din: str) -> Optional[HealthCanadaProduct]:
        """
        Get product by Drug Identification Number (DIN).

        Args:
            din: 8-digit Drug Identification Number

        Returns:
            HealthCanadaProduct if found
        """
        try:
            response = await self._make_request(
                f"{self.ENDPOINTS['drug_product']}",
                params={"din": din},
            )

            if response and len(response) > 0:
                return self._parse_product(response[0])

            return None

        except Exception as e:
            logger.error(f"Error getting product by DIN {din}: {e}")
            return None

    async def get_product_by_code(self, drug_code: str) -> Optional[HealthCanadaProduct]:
        """
        Get product by internal drug code.

        Args:
            drug_code: Health Canada internal drug code

        Returns:
            HealthCanadaProduct if found
        """
        try:
            response = await self._make_request(
                f"{self.ENDPOINTS['drug_product']}",
                params={"id": drug_code},
            )

            if response and len(response) > 0:
                product = self._parse_product(response[0])

                # Fetch additional details
                await self._enrich_product(product, drug_code)

                return product

            return None

        except Exception as e:
            logger.error(f"Error getting product by code {drug_code}: {e}")
            return None

    async def _enrich_product(self, product: HealthCanadaProduct, drug_code: str):
        """Enrich product with additional API data."""
        try:
            # Get active ingredients
            ingredients = await self._make_request(
                self.ENDPOINTS['active_ingredient'],
                params={"id": drug_code},
            )
            if ingredients:
                product.active_ingredients = [
                    {
                        "ingredient": i.get("ingredient_name", ""),
                        "strength": i.get("strength", ""),
                        "strength_unit": i.get("strength_unit", ""),
                    }
                    for i in ingredients
                ]

            # Get route of administration
            routes = await self._make_request(
                self.ENDPOINTS['route'],
                params={"id": drug_code},
            )
            if routes:
                product.route_of_administration = routes[0].get("route_of_administration_name")

            # Get dosage form
            forms = await self._make_request(
                self.ENDPOINTS['form'],
                params={"id": drug_code},
            )
            if forms:
                product.dosage_form = forms[0].get("pharmaceutical_form_name")

            # Get therapeutic class
            classes = await self._make_request(
                self.ENDPOINTS['therapeutic_class'],
                params={"id": drug_code},
            )
            if classes:
                product.therapeutic_class = classes[0].get("tc_atc_number")
                product.atc_code = classes[0].get("tc_atc_number")

        except Exception as e:
            logger.warning(f"Error enriching product {drug_code}: {e}")

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Make API request to Health Canada DPD."""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return []
                    else:
                        logger.warning(f"Health Canada API returned {response.status}")
                        return None

        except Exception as e:
            logger.error(f"Health Canada API request failed: {e}")
            return None

    def _parse_product(self, data: Dict[str, Any]) -> HealthCanadaProduct:
        """Parse API response into HealthCanadaProduct."""
        # Map status string to enum
        status_map = {
            "MARKETED": HealthCanadaStatus.MARKETED,
            "APPROVED": HealthCanadaStatus.APPROVED,
            "CANCELLED POST MARKET": HealthCanadaStatus.CANCELLED_POST,
            "CANCELLED PRE MARKET": HealthCanadaStatus.CANCELLED_PRE,
            "DORMANT": HealthCanadaStatus.DORMANT,
        }

        class_map = {
            "Human": HealthCanadaClass.HUMAN,
            "Veterinary": HealthCanadaClass.VETERINARY,
            "Disinfectant": HealthCanadaClass.DISINFECTANT,
        }

        status_str = data.get("status", "").upper()
        status = status_map.get(status_str, HealthCanadaStatus.MARKETED)

        class_str = data.get("class", "Human")
        drug_class = class_map.get(class_str, HealthCanadaClass.HUMAN)

        first_market = self._parse_date(data.get("first_market_date"))
        last_update = self._parse_date(data.get("last_update_date"))

        return HealthCanadaProduct(
            drug_identification_number=data.get("drug_identification_number", ""),
            brand_name=data.get("brand_name", ""),
            company_name=data.get("company_name", ""),
            drug_class=drug_class,
            status=status,
            first_market_date=first_market,
            last_update_date=last_update,
            ai_group_number=data.get("ai_group_no"),
        )

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string."""
        if not date_str:
            return None

        formats = ["%Y-%m-%d", "%d-%b-%Y", "%Y%m%d"]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue

        return None

    async def health_check(self) -> bool:
        """
        Check if the Health Canada DPD API is healthy and accessible.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            # Try a simple search to verify API is accessible
            response = await self._make_request(
                self.ENDPOINTS['drug_product'],
                params={"brandname": "aspirin"},
            )
            return response is not None
        except Exception as e:
            logger.warning(f"Health Canada API health check failed: {e}")
            return False

    async def get_approval_status(
        self,
        active_substance: str,
    ) -> Dict[str, Any]:
        """
        Get Canadian approval status for an active substance.

        Returns approval status and all marketed products.
        """
        products = await self.search_products(
            active_substance,
            limit=50,
        )

        marketed = [p for p in products if p.status == HealthCanadaStatus.MARKETED]
        approved = [p for p in products if p.status == HealthCanadaStatus.APPROVED]

        first_market_date = None
        if marketed or approved:
            dates = [
                p.first_market_date
                for p in (marketed + approved)
                if p.first_market_date
            ]
            if dates:
                first_market_date = min(dates)

        return {
            "active_substance": active_substance,
            "region": "Canada",
            "approved": len(marketed) > 0 or len(approved) > 0,
            "marketed_count": len(marketed),
            "first_market_date": first_market_date.isoformat() if first_market_date else None,
            "products": [p.to_dict() for p in products],
        }
