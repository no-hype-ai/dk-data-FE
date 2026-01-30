"""
Global Regulatory Service for multi-region approval tracking.

Implements:
- T132: GlobalRegulatoryService class
- T133: get_global_approval_status() for FDA/EMA/HC
- T134: get_label_comparison() for FDA vs EMA SmPC
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
import asyncio
from loguru import logger

from ..external_apis.ema_client import EMAClient
from ..external_apis.health_canada_client import HealthCanadaClient
from ..external_apis.openfda_client import OpenFDAClient


class RegulatoryRegion(str, Enum):
    """Regulatory regions."""
    US = "US"  # FDA
    EU = "EU"  # EMA
    CANADA = "Canada"  # Health Canada
    UK = "UK"  # MHRA (post-Brexit)
    JAPAN = "Japan"  # PMDA (deferred)
    CHINA = "China"  # NMPA (deferred)


class ApprovalStatus(str, Enum):
    """Approval status across regions."""
    APPROVED = "approved"
    PENDING = "pending"
    WITHDRAWN = "withdrawn"
    NOT_SUBMITTED = "not_submitted"
    REFUSED = "refused"
    UNDER_REVIEW = "under_review"


@dataclass
class RegionalApproval:
    """Approval information for a specific region."""
    region: RegulatoryRegion
    status: ApprovalStatus
    approval_date: Optional[date] = None
    application_number: Optional[str] = None
    brand_name: Optional[str] = None
    marketing_authorization_holder: Optional[str] = None
    approved_indications: List[str] = field(default_factory=list)
    label_url: Optional[str] = None
    source: str = ""
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "region": self.region.value,
            "status": self.status.value,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "application_number": self.application_number,
            "brand_name": self.brand_name,
            "marketing_authorization_holder": self.marketing_authorization_holder,
            "approved_indications": self.approved_indications,
            "label_url": self.label_url,
            "source": self.source,
        }


@dataclass
class LabelDifference:
    """Difference between regulatory labels."""
    section: str
    fda_text: Optional[str] = None
    ema_text: Optional[str] = None
    difference_type: str = "content"  # content, missing, additional
    significance: str = "minor"  # minor, moderate, major


@dataclass
class LabelComparison:
    """Comparison of FDA and EMA labels."""
    molecule_name: str
    fda_label_date: Optional[date] = None
    ema_smpc_date: Optional[date] = None
    differences: List[LabelDifference] = field(default_factory=list)
    indication_alignment_score: float = 0.0
    warning_alignment_score: float = 0.0
    dosing_differences: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "molecule_name": self.molecule_name,
            "fda_label_date": self.fda_label_date.isoformat() if self.fda_label_date else None,
            "ema_smpc_date": self.ema_smpc_date.isoformat() if self.ema_smpc_date else None,
            "differences_count": len(self.differences),
            "differences": [
                {
                    "section": d.section,
                    "difference_type": d.difference_type,
                    "significance": d.significance,
                }
                for d in self.differences
            ],
            "indication_alignment_score": self.indication_alignment_score,
            "warning_alignment_score": self.warning_alignment_score,
            "dosing_differences": self.dosing_differences,
        }


@dataclass
class GlobalApprovalStatus:
    """Global approval status across all tracked regions."""
    molecule_name: str
    molecule_id: str
    regional_approvals: Dict[str, RegionalApproval]
    first_global_approval: Optional[date] = None
    first_approval_region: Optional[RegulatoryRegion] = None
    total_approved_regions: int = 0
    pending_regions: List[RegulatoryRegion] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "molecule_name": self.molecule_name,
            "molecule_id": self.molecule_id,
            "regional_approvals": {
                region: approval.to_dict()
                for region, approval in self.regional_approvals.items()
            },
            "first_global_approval": self.first_global_approval.isoformat() if self.first_global_approval else None,
            "first_approval_region": self.first_approval_region.value if self.first_approval_region else None,
            "total_approved_regions": self.total_approved_regions,
            "pending_regions": [r.value for r in self.pending_regions],
            "timestamp": self.timestamp.isoformat(),
        }


class GlobalRegulatoryService:
    """
    Service for tracking global regulatory approvals.

    Currently supports:
    - FDA (US)
    - EMA (EU)
    - Health Canada (Canada)

    Deferred (pending partnerships):
    - PMDA (Japan)
    - NMPA (China)
    - MHRA (UK)
    """

    def __init__(
        self,
        ema_client: Optional[EMAClient] = None,
        health_canada_client: Optional[HealthCanadaClient] = None,
        openfda_client: Optional[OpenFDAClient] = None,
    ):
        self._ema = ema_client or EMAClient()
        self._health_canada = health_canada_client or HealthCanadaClient()
        self._openfda = openfda_client or OpenFDAClient()

    async def get_global_approval_status(
        self,
        molecule_name: str,
        molecule_id: Optional[str] = None,
        regions: Optional[List[RegulatoryRegion]] = None,
    ) -> GlobalApprovalStatus:
        """
        Get approval status across all supported regions.

        Args:
            molecule_name: Name of the drug/molecule
            molecule_id: Optional identifier
            regions: Specific regions to check (default: all supported)

        Returns:
            GlobalApprovalStatus with approvals per region
        """
        logger.info(f"Getting global regulatory status for {molecule_name}")

        if regions is None:
            regions = [RegulatoryRegion.US, RegulatoryRegion.EU, RegulatoryRegion.CANADA]

        # Query all regions in parallel
        tasks = []
        for region in regions:
            if region == RegulatoryRegion.US:
                tasks.append(self._get_fda_approval(molecule_name))
            elif region == RegulatoryRegion.EU:
                tasks.append(self._get_ema_approval(molecule_name))
            elif region == RegulatoryRegion.CANADA:
                tasks.append(self._get_health_canada_approval(molecule_name))
            else:
                # Unsupported region
                tasks.append(self._get_unsupported_region(region))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        regional_approvals: Dict[str, RegionalApproval] = {}
        approved_dates: List[tuple] = []

        for region, result in zip(regions, results):
            if isinstance(result, Exception):
                logger.warning(f"Error getting approval for {region}: {result}")
                regional_approvals[region.value] = RegionalApproval(
                    region=region,
                    status=ApprovalStatus.NOT_SUBMITTED,
                    source="error",
                )
            else:
                regional_approvals[region.value] = result
                if result.status == ApprovalStatus.APPROVED and result.approval_date:
                    approved_dates.append((result.approval_date, region))

        # Determine first approval
        first_approval_date = None
        first_approval_region = None
        if approved_dates:
            approved_dates.sort(key=lambda x: x[0])
            first_approval_date, first_approval_region = approved_dates[0]

        # Count approvals
        approved_count = sum(
            1 for a in regional_approvals.values()
            if a.status == ApprovalStatus.APPROVED
        )

        # Find pending regions
        pending = [
            a.region for a in regional_approvals.values()
            if a.status in [ApprovalStatus.PENDING, ApprovalStatus.UNDER_REVIEW]
        ]

        return GlobalApprovalStatus(
            molecule_name=molecule_name,
            molecule_id=molecule_id or molecule_name.upper().replace(" ", "_"),
            regional_approvals=regional_approvals,
            first_global_approval=first_approval_date,
            first_approval_region=first_approval_region,
            total_approved_regions=approved_count,
            pending_regions=pending,
        )

    async def _get_fda_approval(self, molecule_name: str) -> RegionalApproval:
        """Get FDA approval status."""
        try:
            labels = await self._openfda.get_drug_label(molecule_name)

            if labels:
                label = labels[0]
                openfda = label.get("openfda", {})

                # Extract approval information
                brand_names = openfda.get("brand_name", [])
                manufacturers = openfda.get("manufacturer_name", [])
                application_numbers = openfda.get("application_number", [])

                # Parse effective date
                effective_date = label.get("effective_time")
                approval_date = None
                if effective_date:
                    try:
                        approval_date = datetime.strptime(effective_date, "%Y%m%d").date()
                    except ValueError:
                        pass

                # Extract indications
                indications = label.get("indications_and_usage", [])

                return RegionalApproval(
                    region=RegulatoryRegion.US,
                    status=ApprovalStatus.APPROVED,
                    approval_date=approval_date,
                    application_number=application_numbers[0] if application_numbers else None,
                    brand_name=brand_names[0] if brand_names else None,
                    marketing_authorization_holder=manufacturers[0] if manufacturers else None,
                    approved_indications=indications[:5],  # Limit to first 5
                    label_url=f"https://dailymed.nlm.nih.gov/dailymed/search.cfm?query={molecule_name}",
                    source="openfda",
                )

            return RegionalApproval(
                region=RegulatoryRegion.US,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="openfda",
            )

        except Exception as e:
            logger.error(f"Error getting FDA approval: {e}")
            return RegionalApproval(
                region=RegulatoryRegion.US,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="error",
            )

    async def _get_ema_approval(self, molecule_name: str) -> RegionalApproval:
        """Get EMA approval status."""
        try:
            products = await self._ema.search_products(molecule_name, limit=1)

            if products:
                product = products[0]

                # Map EMA status to our status
                status = ApprovalStatus.APPROVED
                if product.status.value == "withdrawn":
                    status = ApprovalStatus.WITHDRAWN
                elif product.status.value == "refused":
                    status = ApprovalStatus.REFUSED

                return RegionalApproval(
                    region=RegulatoryRegion.EU,
                    status=status,
                    approval_date=product.authorization_date,
                    application_number=product.authorization_number,
                    brand_name=product.product_name,
                    marketing_authorization_holder=product.marketing_authorization_holder,
                    approved_indications=product.conditions,
                    label_url=product.smpc_url,
                    source="ema",
                )

            return RegionalApproval(
                region=RegulatoryRegion.EU,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="ema",
            )

        except Exception as e:
            logger.error(f"Error getting EMA approval: {e}")
            return RegionalApproval(
                region=RegulatoryRegion.EU,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="error",
            )

    async def _get_health_canada_approval(self, molecule_name: str) -> RegionalApproval:
        """Get Health Canada approval status."""
        try:
            approval_status = await self._health_canada.get_approval_status(molecule_name)

            if approval_status.get("approved"):
                products = approval_status.get("products", [])
                first_product = products[0] if products else {}

                return RegionalApproval(
                    region=RegulatoryRegion.CANADA,
                    status=ApprovalStatus.APPROVED,
                    approval_date=datetime.fromisoformat(approval_status["first_market_date"]).date() if approval_status.get("first_market_date") else None,
                    application_number=first_product.get("din"),
                    brand_name=first_product.get("brand_name"),
                    marketing_authorization_holder=first_product.get("company_name"),
                    source="health_canada",
                )

            return RegionalApproval(
                region=RegulatoryRegion.CANADA,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="health_canada",
            )

        except Exception as e:
            logger.error(f"Error getting Health Canada approval: {e}")
            return RegionalApproval(
                region=RegulatoryRegion.CANADA,
                status=ApprovalStatus.NOT_SUBMITTED,
                source="error",
            )

    async def _get_unsupported_region(self, region: RegulatoryRegion) -> RegionalApproval:
        """Return placeholder for unsupported regions."""
        return RegionalApproval(
            region=region,
            status=ApprovalStatus.NOT_SUBMITTED,
            source="unsupported",
        )

    async def get_label_comparison(
        self,
        molecule_name: str,
    ) -> LabelComparison:
        """
        Compare FDA label with EMA SmPC.

        Identifies differences in:
        - Approved indications
        - Dosing recommendations
        - Warnings and precautions
        - Contraindications
        """
        logger.info(f"Comparing FDA vs EMA labels for {molecule_name}")

        # Get FDA label
        fda_labels = await self._openfda.get_drug_label(molecule_name)
        fda_label = fda_labels[0] if fda_labels else None

        # Get EMA SmPC
        ema_smpc = await self._ema.get_smpc(molecule_name)

        comparison = LabelComparison(molecule_name=molecule_name)

        # Parse FDA label date
        if fda_label:
            effective_time = fda_label.get("effective_time")
            if effective_time:
                try:
                    comparison.fda_label_date = datetime.strptime(effective_time, "%Y%m%d").date()
                except ValueError:
                    pass

        # Parse EMA SmPC date (from revision date)
        if ema_smpc:
            # SmPC date would come from parsed document
            pass

        # Compare indications
        fda_indications = fda_label.get("indications_and_usage", []) if fda_label else []
        ema_indications = ema_smpc.get("sections", {}).get("indications", []) if ema_smpc else []

        if fda_indications and ema_indications:
            # Calculate simple alignment score based on text overlap
            fda_text = " ".join(fda_indications).lower()
            ema_text = " ".join(ema_indications).lower()
            fda_words = set(fda_text.split())
            ema_words = set(ema_text.split())

            if fda_words and ema_words:
                overlap = len(fda_words & ema_words)
                total = len(fda_words | ema_words)
                comparison.indication_alignment_score = overlap / total if total > 0 else 0

        # Compare warnings
        fda_warnings = fda_label.get("warnings_and_cautions", []) if fda_label else []
        ema_warnings = ema_smpc.get("sections", {}).get("warnings", []) if ema_smpc else []

        if fda_warnings and ema_warnings:
            fda_text = " ".join(fda_warnings).lower()
            ema_text = " ".join(ema_warnings).lower()
            fda_words = set(fda_text.split())
            ema_words = set(ema_text.split())

            if fda_words and ema_words:
                overlap = len(fda_words & ema_words)
                total = len(fda_words | ema_words)
                comparison.warning_alignment_score = overlap / total if total > 0 else 0

        # Identify dosing differences
        fda_dosage = fda_label.get("dosage_and_administration", []) if fda_label else []
        ema_dosage = ema_smpc.get("sections", {}).get("posology", []) if ema_smpc else []

        # Note major differences
        if fda_dosage and not ema_dosage:
            comparison.differences.append(LabelDifference(
                section="dosing",
                fda_text=fda_dosage[0][:200] if fda_dosage else None,
                difference_type="missing",
                significance="moderate",
            ))
        elif ema_dosage and not fda_dosage:
            comparison.differences.append(LabelDifference(
                section="dosing",
                ema_text=ema_dosage[0][:200] if ema_dosage else None,
                difference_type="missing",
                significance="moderate",
            ))

        return comparison

    async def get_regional_details(
        self,
        molecule_name: str,
        region: RegulatoryRegion,
    ) -> Dict[str, Any]:
        """
        Get detailed regulatory information for a specific region.
        """
        if region == RegulatoryRegion.US:
            approval = await self._get_fda_approval(molecule_name)
            labels = await self._openfda.get_drug_label(molecule_name)
            return {
                "approval": approval.to_dict(),
                "labels_count": len(labels),
                "source": "openfda",
            }
        elif region == RegulatoryRegion.EU:
            approval = await self._get_ema_approval(molecule_name)
            products = await self._ema.search_products(molecule_name)
            return {
                "approval": approval.to_dict(),
                "products_count": len(products),
                "products": [p.to_dict() for p in products[:5]],
                "source": "ema",
            }
        elif region == RegulatoryRegion.CANADA:
            approval = await self._get_health_canada_approval(molecule_name)
            status = await self._health_canada.get_approval_status(molecule_name)
            return {
                "approval": approval.to_dict(),
                "products_count": status.get("marketed_count", 0),
                "source": "health_canada",
            }
        else:
            return {
                "error": f"Region {region.value} not supported",
            }
