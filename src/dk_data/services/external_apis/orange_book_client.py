"""
FDA Orange Book API Client.

Provides access to FDA Orange Book data:
- Approved drug products with therapeutic equivalence evaluations
- Patent information (expiry dates, drug substance, drug product patents)
- Exclusivity information (new chemical entity, orphan drug, pediatric)

Data Source: https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

The Orange Book is published in downloadable text/zip files rather than a REST API.
This client downloads and parses these files.
"""

import os
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from enum import Enum
import asyncio

import aiohttp
from loguru import logger


class ExclusivityCode(str, Enum):
    """Orange Book exclusivity codes."""
    NCE = "NCE"  # New Chemical Entity - 5 years
    ODE = "ODE"  # Orphan Drug Exclusivity - 7 years
    PED = "PED"  # Pediatric Exclusivity - 6 months added
    I = "I"      # 180-day generic exclusivity
    NP = "NP"    # New Patient Population
    NDF = "NDF"  # New Dosage Form
    NC = "NC"    # New Combination


class TherapeuticEquivalence(str, Enum):
    """Therapeutic equivalence ratings."""
    AA = "AA"  # Products in conventional dosage forms
    AB = "AB"  # Therapeutically equivalent
    AN = "AN"  # Aerosol/metered
    AO = "AO"  # Injectable oil solutions
    AP = "AP"  # Injectable aqueous solutions
    AT = "AT"  # Topical products
    BC = "BC"  # Extended release dosage forms
    BD = "BD"  # Active ingredients and dosage forms with bioequivalence problems
    BE = "BE"  # Enteric coated products
    BN = "BN"  # Products in aerosol-nebulizer
    BP = "BP"  # Active ingredients and dosage forms with bioequivalence problems
    BR = "BR"  # Suppositories
    BS = "BS"  # Extended release capsules
    BT = "BT"  # Topical products with bioequivalence issues
    BX = "BX"  # Insufficient data for equivalence


@dataclass
class OrangeBookProduct:
    """Orange Book approved drug product."""
    appl_no: str  # NDA/ANDA/BLA number
    product_no: str
    trade_name: str
    ingredient: str
    applicant: str  # Company name
    strength: str
    dosage_form: str
    route: str
    te_code: Optional[str] = None  # Therapeutic equivalence
    approval_date: Optional[date] = None
    rld: bool = False  # Reference Listed Drug
    rs: bool = False   # Reference Standard
    type: str = "RX"   # RX, OTC, DISCN (discontinued)
    applicant_full_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appl_no": self.appl_no,
            "product_no": self.product_no,
            "trade_name": self.trade_name,
            "ingredient": self.ingredient,
            "applicant": self.applicant,
            "strength": self.strength,
            "dosage_form": self.dosage_form,
            "route": self.route,
            "te_code": self.te_code,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "rld": self.rld,
            "rs": self.rs,
            "type": self.type,
        }


@dataclass
class OrangeBookPatent:
    """Orange Book patent information."""
    appl_no: str
    product_no: str
    patent_no: str
    patent_expire_date: Optional[date] = None
    drug_substance_flag: bool = False  # Claim covers drug substance
    drug_product_flag: bool = False    # Claim covers drug product
    patent_use_code: Optional[str] = None
    delist_flag: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appl_no": self.appl_no,
            "product_no": self.product_no,
            "patent_no": self.patent_no,
            "patent_expire_date": self.patent_expire_date.isoformat() if self.patent_expire_date else None,
            "drug_substance_flag": self.drug_substance_flag,
            "drug_product_flag": self.drug_product_flag,
            "patent_use_code": self.patent_use_code,
            "delist_flag": self.delist_flag,
        }


@dataclass
class OrangeBookExclusivity:
    """Orange Book exclusivity information."""
    appl_no: str
    product_no: str
    exclusivity_code: str
    exclusivity_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appl_no": self.appl_no,
            "product_no": self.product_no,
            "exclusivity_code": self.exclusivity_code,
            "exclusivity_date": self.exclusivity_date.isoformat() if self.exclusivity_date else None,
        }


class OrangeBookClient:
    """
    Client for FDA Orange Book data.

    Downloads and parses Orange Book data files from FDA website.
    """

    # FDA Orange Book download URLs
    BASE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files"
    DATA_URL = "https://www.fda.gov/media/76860/download"  # products.txt
    PATENT_URL = "https://www.fda.gov/media/76861/download"  # patent.txt
    EXCLUSIVITY_URL = "https://www.fda.gov/media/76862/download"  # exclusivity.txt

    # Alternative: Full zip download
    ZIP_URL = "https://www.accessdata.fda.gov/cder/ob.zip"

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).parent / "data" / "orange_book"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._products: List[OrangeBookProduct] = []
        self._patents: List[OrangeBookPatent] = []
        self._exclusivities: List[OrangeBookExclusivity] = []
        self._loaded = False

    async def health_check(self) -> bool:
        """Check if Orange Book data is accessible."""
        # Check local cache first
        products_file = self.cache_dir / "products.txt"
        if products_file.exists():
            return True

        # Try to access FDA download
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    self.ZIP_URL,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def download_data(self, force: bool = False) -> bool:
        """Download Orange Book data files from FDA."""
        products_file = self.cache_dir / "products.txt"

        if products_file.exists() and not force:
            logger.info("Orange Book data already cached")
            return True

        logger.info("Downloading Orange Book data from FDA...")

        try:
            async with aiohttp.ClientSession() as session:
                # Download the zip file
                async with session.get(
                    self.ZIP_URL,
                    timeout=aiohttp.ClientTimeout(total=300),
                    allow_redirects=True
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download: HTTP {response.status}")
                        return False

                    content = await response.read()

            # Extract zip contents
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if name.endswith('.txt'):
                        # Extract to cache dir with simple name
                        target_name = name.split('/')[-1].lower()
                        with zf.open(name) as src:
                            (self.cache_dir / target_name).write_bytes(src.read())

            logger.info(f"Orange Book data downloaded to {self.cache_dir}")
            return True

        except Exception as e:
            logger.error(f"Error downloading Orange Book data: {e}")
            return False

    async def load_data(self, force_download: bool = False) -> bool:
        """Load Orange Book data from cache or download."""
        if self._loaded and not force_download:
            return True

        # Download if needed
        products_file = self.cache_dir / "products.txt"
        if not products_file.exists() or force_download:
            success = await self.download_data(force=force_download)
            if not success:
                return False

        # Parse products
        self._products = self._parse_products()

        # Parse patents
        self._patents = self._parse_patents()

        # Parse exclusivities
        self._exclusivities = self._parse_exclusivities()

        self._loaded = True
        logger.info(f"Loaded {len(self._products)} products, {len(self._patents)} patents, {len(self._exclusivities)} exclusivities")
        return True

    def _parse_products(self) -> List[OrangeBookProduct]:
        """Parse products.txt file."""
        products_file = self.cache_dir / "products.txt"
        if not products_file.exists():
            return []

        products = []
        try:
            with open(products_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()

            # Skip header line
            for line in lines[1:]:
                fields = line.strip().split('~')
                if len(fields) < 10:
                    continue

                try:
                    approval_date = None
                    if fields[8] and fields[8] != "Approved Prior to Jan 1, 1982":
                        try:
                            approval_date = datetime.strptime(fields[8], "%b %d, %Y").date()
                        except:
                            pass

                    product = OrangeBookProduct(
                        ingredient=fields[0],
                        dosage_form=fields[1] if len(fields) > 1 else "",
                        route=fields[2] if len(fields) > 2 else "",
                        trade_name=fields[3] if len(fields) > 3 else "",
                        applicant=fields[4] if len(fields) > 4 else "",
                        strength=fields[5] if len(fields) > 5 else "",
                        appl_no=fields[6] if len(fields) > 6 else "",
                        product_no=fields[7] if len(fields) > 7 else "",
                        approval_date=approval_date,
                        te_code=fields[9] if len(fields) > 9 else None,
                        rld=fields[10] == "RLD" if len(fields) > 10 else False,
                        rs=fields[11] == "RS" if len(fields) > 11 else False,
                        type=fields[12] if len(fields) > 12 else "RX",
                        applicant_full_name=fields[13] if len(fields) > 13 else None,
                    )
                    products.append(product)
                except Exception as e:
                    continue

        except Exception as e:
            logger.error(f"Error parsing products: {e}")

        return products

    def _parse_patents(self) -> List[OrangeBookPatent]:
        """Parse patent.txt file."""
        patent_file = self.cache_dir / "patent.txt"
        if not patent_file.exists():
            return []

        patents = []
        try:
            with open(patent_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()

            for line in lines[1:]:
                fields = line.strip().split('~')
                if len(fields) < 7:
                    continue

                try:
                    expire_date = None
                    if fields[4]:
                        try:
                            expire_date = datetime.strptime(fields[4], "%b %d, %Y").date()
                        except:
                            pass

                    patent = OrangeBookPatent(
                        appl_no=fields[0],
                        product_no=fields[1],
                        patent_no=fields[2],
                        patent_expire_date=expire_date,
                        drug_substance_flag=fields[5] == "Y" if len(fields) > 5 else False,
                        drug_product_flag=fields[6] == "Y" if len(fields) > 6 else False,
                        patent_use_code=fields[7] if len(fields) > 7 else None,
                        delist_flag=fields[8] == "Y" if len(fields) > 8 else False,
                    )
                    patents.append(patent)
                except Exception as e:
                    continue

        except Exception as e:
            logger.error(f"Error parsing patents: {e}")

        return patents

    def _parse_exclusivities(self) -> List[OrangeBookExclusivity]:
        """Parse exclusivity.txt file."""
        excl_file = self.cache_dir / "exclusivity.txt"
        if not excl_file.exists():
            return []

        exclusivities = []
        try:
            with open(excl_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()

            for line in lines[1:]:
                fields = line.strip().split('~')
                if len(fields) < 4:
                    continue

                try:
                    excl_date = None
                    if fields[3]:
                        try:
                            excl_date = datetime.strptime(fields[3], "%b %d, %Y").date()
                        except:
                            pass

                    excl = OrangeBookExclusivity(
                        appl_no=fields[0],
                        product_no=fields[1],
                        exclusivity_code=fields[2],
                        exclusivity_date=excl_date,
                    )
                    exclusivities.append(excl)
                except:
                    continue

        except Exception as e:
            logger.error(f"Error parsing exclusivities: {e}")

        return exclusivities

    async def search_products(
        self,
        query: str,
        limit: int = 100
    ) -> List[OrangeBookProduct]:
        """Search for products by name, ingredient, or applicant."""
        await self.load_data()

        query_lower = query.lower()
        matches = []

        for product in self._products:
            if (query_lower in product.trade_name.lower() or
                query_lower in product.ingredient.lower() or
                query_lower in product.applicant.lower()):
                matches.append(product)
                if len(matches) >= limit:
                    break

        return matches

    async def get_product(self, appl_no: str, product_no: str = "001") -> Optional[OrangeBookProduct]:
        """Get a specific product by application number."""
        await self.load_data()

        for product in self._products:
            if product.appl_no == appl_no and product.product_no == product_no:
                return product
        return None

    async def get_patents_for_product(self, appl_no: str) -> List[OrangeBookPatent]:
        """Get all patents for a product."""
        await self.load_data()
        return [p for p in self._patents if p.appl_no == appl_no]

    async def get_exclusivities_for_product(self, appl_no: str) -> List[OrangeBookExclusivity]:
        """Get all exclusivities for a product."""
        await self.load_data()
        return [e for e in self._exclusivities if e.appl_no == appl_no]

    async def get_all_products(self) -> List[OrangeBookProduct]:
        """Get all products."""
        await self.load_data()
        return self._products

    async def get_all_patents(self) -> List[OrangeBookPatent]:
        """Get all patents."""
        await self.load_data()
        return self._patents

    async def get_all_exclusivities(self) -> List[OrangeBookExclusivity]:
        """Get all exclusivities."""
        await self.load_data()
        return self._exclusivities


# Factory function
async def get_orange_book_client() -> OrangeBookClient:
    """Get Orange Book client instance."""
    client = OrangeBookClient()
    await client.load_data()
    return client
