"""
Market Intelligence Models.

Data models for SEC EDGAR filings, product revenues, and pipeline assets.
Used by sec_edgar_client.py for structured extraction from 10-K/20-F filings.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class Filing:
    """SEC EDGAR filing metadata."""

    accession: str
    filing_date: date
    form: str  # 10-K, 10-Q, 20-F, 8-K
    document_url: Optional[str] = None
    company_cik: Optional[str] = None
    primary_document: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accession": self.accession,
            "filing_date": self.filing_date.isoformat(),
            "form": self.form,
            "document_url": self.document_url,
            "company_cik": self.company_cik,
            "primary_document": self.primary_document,
        }


@dataclass
class ProductRevenue:
    """Product-level revenue extracted from SEC filings."""

    product_name: str
    revenue_usd: float  # Revenue in millions USD
    period: str  # annual, quarterly
    year: Optional[int] = None
    source_filing: Optional[str] = None
    yoy_growth: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_name": self.product_name,
            "revenue_usd": self.revenue_usd,
            "period": self.period,
            "year": self.year,
            "source_filing": self.source_filing,
            "yoy_growth": self.yoy_growth,
        }


@dataclass
class PipelineAsset:
    """Pipeline asset extracted from 10-K Business section."""

    compound_name: str
    phase: Optional[str] = None  # Pre-clinical, Phase 1, Phase 2, Phase 3, NDA/BLA
    indication: Optional[str] = None
    target: Optional[str] = None
    partner: Optional[str] = None
    status: Optional[str] = None
    filing_accession: Optional[str] = None
    extract_confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compound_name": self.compound_name,
            "phase": self.phase,
            "indication": self.indication,
            "target": self.target,
            "partner": self.partner,
            "status": self.status,
            "filing_accession": self.filing_accession,
            "extract_confidence": self.extract_confidence,
        }
