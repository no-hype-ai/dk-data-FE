"""
European Medicines Agency (EMA) API Client.

Implements T130: EMAClient class for accessing EMA product data.

Data sources:
- EMA Public Data: https://www.ema.europa.eu/en/medicines/download-medicine-data
- EMA API (limited): https://www.ema.europa.eu/en/about-us/how-we-work/big-data/ema-computerised-systems
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
import aiohttp
from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient


class EMAAuthorizationType(str, Enum):
    """EMA authorization types."""
    CENTRALISED = "centralised"  # EU-wide authorization
    NATIONAL = "national"  # Individual member state
    MUTUAL_RECOGNITION = "mutual_recognition"  # MRP
    DECENTRALISED = "decentralised"  # DCP


class EMAStatus(str, Enum):
    """EMA authorization status."""
    AUTHORIZED = "authorized"
    WITHDRAWN = "withdrawn"
    SUSPENDED = "suspended"
    REFUSED = "refused"
    UNDER_REVIEW = "under_review"


@dataclass
class EMAProduct:
    """EMA authorized product information."""
    product_name: str
    active_substance: str
    inn: Optional[str] = None  # International Nonproprietary Name
    authorization_number: Optional[str] = None
    authorization_date: Optional[date] = None
    authorization_type: EMAAuthorizationType = EMAAuthorizationType.CENTRALISED
    status: EMAStatus = EMAStatus.AUTHORIZED
    therapeutic_area: Optional[str] = None
    atc_code: Optional[str] = None
    marketing_authorization_holder: Optional[str] = None
    orphan_medicine: bool = False
    biosimilar: bool = False
    generic: bool = False
    conditions: List[str] = field(default_factory=list)
    smpc_url: Optional[str] = None  # Summary of Product Characteristics
    epar_url: Optional[str] = None  # European Public Assessment Report
    revision_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "product_name": self.product_name,
            "active_substance": self.active_substance,
            "inn": self.inn,
            "authorization_number": self.authorization_number,
            "authorization_date": self.authorization_date.isoformat() if self.authorization_date else None,
            "authorization_type": self.authorization_type.value,
            "status": self.status.value,
            "therapeutic_area": self.therapeutic_area,
            "atc_code": self.atc_code,
            "marketing_authorization_holder": self.marketing_authorization_holder,
            "orphan_medicine": self.orphan_medicine,
            "biosimilar": self.biosimilar,
            "generic": self.generic,
            "conditions": self.conditions,
            "smpc_url": self.smpc_url,
            "epar_url": self.epar_url,
        }


@dataclass
class EMASafetyAlert:
    """EMA safety communication."""
    title: str
    date: date
    alert_type: str  # e.g., "DHPC", "PRAC recommendation"
    product_name: str
    active_substance: Optional[str] = None
    summary: Optional[str] = None
    url: Optional[str] = None


class EMAClient(BaseAPIClient):
    """
    Client for accessing EMA medicine data.

    Note: EMA does not provide a comprehensive public API.
    This client uses:
    1. EMA public medicine data (downloadable Excel/CSV files)
    2. EMA RSS feeds for updates
    3. Web scraping for specific product pages (when needed)
    """

    # EMA data endpoints
    BASE_URL = "https://www.ema.europa.eu"
    MEDICINES_DATA_URL = f"{BASE_URL}/en/medicines/download-medicine-data"

    # RSS feeds
    RSS_HUMAN_MEDICINES = f"{BASE_URL}/en/feeds/medicines/human/epar/index.xml"
    RSS_SAFETY_ALERTS = f"{BASE_URL}/en/feeds/pharmacovigilance/signal-management/index.xml"

    def __init__(self, cache_ttl: int = 86400):  # 24 hour cache
        config = APIClientConfig(
            base_url=self.BASE_URL,
            timeout=30.0,
            max_retries=3,
            requests_per_second=1.0,  # 1 request per second
            cache_ttl=cache_ttl,
        )
        super().__init__(config)
        self._products_cache: Dict[str, EMAProduct] = {}
        self._last_data_refresh: Optional[datetime] = None

    async def health_check(self) -> bool:
        """
        Check if EMA data is available.

        Since EMA doesn't have a standard REST API, we check:
        1. If local data file exists (primary source)
        2. If not, try RSS feed (secondary check)
        """
        import json
        from pathlib import Path

        # Primary: Check local data file
        data_file = Path(__file__).parent / "data" / "ema_medicines.json"
        if data_file.exists():
            try:
                with open(data_file) as f:
                    data = json.load(f)
                if data.get("medicines") and len(data["medicines"]) > 0:
                    logger.debug(f"EMA health check: Local data has {len(data['medicines'])} medicines")
                    return True
            except Exception as e:
                logger.debug(f"EMA local data check failed: {e}")

        # Secondary: Try RSS feed (more reliable than website)
        try:
            response = await self._get("/en/feeds/medicines/human/epar/index.xml")
            if response is not None:
                return True
        except Exception as e:
            logger.debug(f"EMA RSS feed check failed: {e}")

        # EMA data not available via either method
        return False

    async def search_products(
        self,
        query: str,
        limit: int = 20,
        include_withdrawn: bool = False,
    ) -> List[EMAProduct]:
        """
        Search for EMA authorized products.

        Args:
            query: Product name or active substance to search
            limit: Maximum number of results
            include_withdrawn: Include withdrawn products

        Returns:
            List of matching EMA products
        """
        logger.debug(f"Searching EMA products for: {query}")

        # In production, this would query a local database populated
        # from EMA medicine data downloads
        products = await self._query_products_database(query, limit)

        if not include_withdrawn:
            products = [p for p in products if p.status != EMAStatus.WITHDRAWN]

        return products[:limit]

    async def get_product(
        self,
        product_name: str,
    ) -> Optional[EMAProduct]:
        """
        Get detailed product information.

        Args:
            product_name: Name of the product

        Returns:
            EMAProduct if found, None otherwise
        """
        products = await self.search_products(product_name, limit=1)
        return products[0] if products else None

    async def get_authorization_status(
        self,
        active_substance: str,
    ) -> Dict[str, Any]:
        """
        Get authorization status for an active substance.

        Returns authorization status and related products.
        """
        products = await self.search_products(active_substance, limit=50)

        authorized = [p for p in products if p.status == EMAStatus.AUTHORIZED]
        withdrawn = [p for p in products if p.status == EMAStatus.WITHDRAWN]

        return {
            "active_substance": active_substance,
            "authorized_count": len(authorized),
            "withdrawn_count": len(withdrawn),
            "first_authorization_date": min(
                (p.authorization_date for p in authorized if p.authorization_date),
                default=None
            ),
            "products": [p.to_dict() for p in products],
        }

    async def get_smpc(
        self,
        product_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get Summary of Product Characteristics (SmPC).

        The SmPC is the EU equivalent of the US prescribing information.
        """
        product = await self.get_product(product_name)
        if not product or not product.smpc_url:
            return None

        # In production, fetch and parse SmPC document
        return {
            "product_name": product_name,
            "smpc_url": product.smpc_url,
            "sections": [],  # Would contain parsed SmPC sections
        }

    async def get_epar(
        self,
        product_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get European Public Assessment Report (EPAR).

        EPAR contains scientific assessment and regulatory information.
        """
        product = await self.get_product(product_name)
        if not product or not product.epar_url:
            return None

        return {
            "product_name": product_name,
            "epar_url": product.epar_url,
            "authorization_date": product.authorization_date.isoformat() if product.authorization_date else None,
        }

    async def get_safety_alerts(
        self,
        active_substance: Optional[str] = None,
        limit: int = 20,
    ) -> List[EMASafetyAlert]:
        """
        Get recent EMA safety alerts.

        Args:
            active_substance: Filter by active substance (optional)
            limit: Maximum number of alerts

        Returns:
            List of safety alerts
        """
        # In production, parse EMA RSS feed or query local database
        return []

    async def _query_products_database(
        self,
        query: str,
        limit: int,
    ) -> List[EMAProduct]:
        """
        Query the local products database from EMA JSON file.

        Data is loaded from ema_medicines.json which is populated from
        EMA medicine data downloads.
        """
        import json
        from pathlib import Path

        # Load data from JSON file
        data_file = Path(__file__).parent / "data" / "ema_medicines.json"
        if not data_file.exists():
            logger.warning(f"EMA data file not found: {data_file}")
            return []

        try:
            with open(data_file) as f:
                data = json.load(f)

            medicines = data.get("medicines", [])
            query_lower = query.lower()

            # Search by name, active substance, or INN
            matches = []
            for m in medicines:
                name = (m.get("name") or "").lower()
                active = (m.get("active_substance") or "").lower() if isinstance(m.get("active_substance"), str) else ""
                inn = (m.get("inn") or "").lower() if isinstance(m.get("inn"), str) else ""

                if query_lower in name or query_lower in active or query_lower in inn:
                    # Convert to EMAProduct
                    status_map = {
                        "Authorised": EMAStatus.AUTHORIZED,
                        "Withdrawn": EMAStatus.WITHDRAWN,
                        "Suspended": EMAStatus.SUSPENDED,
                        "Refused": EMAStatus.REFUSED,
                    }
                    product = EMAProduct(
                        product_name=m.get("name") or "",
                        active_substance=m.get("active_substance") or "",
                        inn=m.get("inn"),
                        authorization_number=m.get("ema_product_number"),
                        status=status_map.get(m.get("status"), EMAStatus.AUTHORIZED),
                        therapeutic_area=m.get("therapeutic_area"),
                        atc_code=m.get("atc_code"),
                        marketing_authorization_holder=m.get("marketing_auth_holder"),
                        orphan_medicine=m.get("orphan_medicine", False),
                        biosimilar=m.get("biosimilar", False),
                        generic=m.get("generic", False),
                    )
                    matches.append(product)

                    if len(matches) >= limit:
                        break

            logger.info(f"EMA query '{query}' found {len(matches)} matches")
            return matches

        except Exception as e:
            logger.error(f"Error querying EMA data: {e}")
            return []

    async def refresh_products_data(self) -> bool:
        """
        Refresh products data from EMA downloads.

        Should be run monthly to sync with EMA data updates.
        """
        logger.info("Refreshing EMA products data")

        try:
            # In production:
            # 1. Download EMA medicine data Excel file
            # 2. Parse and import into local database
            # 3. Update cache

            self._last_data_refresh = datetime.utcnow()
            return True

        except Exception as e:
            logger.error(f"Failed to refresh EMA data: {e}")
            return False

    async def compare_with_fda(
        self,
        active_substance: str,
        fda_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare EMA authorization with FDA approval.

        Returns differences in:
        - Authorization dates
        - Approved indications
        - Label warnings
        """
        ema_status = await self.get_authorization_status(active_substance)

        comparison = {
            "active_substance": active_substance,
            "ema_authorized": ema_status["authorized_count"] > 0,
            "fda_approved": fda_data.get("approved", False),
            "ema_first_auth_date": ema_status.get("first_authorization_date"),
            "fda_approval_date": fda_data.get("approval_date"),
            "authorization_lag_days": None,
            "indication_differences": [],
        }

        # Calculate authorization lag
        if comparison["ema_first_auth_date"] and comparison["fda_approval_date"]:
            ema_date = comparison["ema_first_auth_date"]
            fda_date = comparison["fda_approval_date"]
            if isinstance(ema_date, str):
                ema_date = date.fromisoformat(ema_date)
            if isinstance(fda_date, str):
                fda_date = date.fromisoformat(fda_date)
            comparison["authorization_lag_days"] = (ema_date - fda_date).days

        return comparison


# Factory function
_ema_client: Optional[EMAClient] = None

async def get_ema_client() -> EMAClient:
    """Get or create EMA client instance."""
    global _ema_client
    if _ema_client is None:
        _ema_client = EMAClient()
    return _ema_client

