"""SEC EDGAR MD&A Section Extractor

Fetches actual filing HTML from EDGAR and extracts:
- Management Discussion & Analysis (Item 7 for 10-K, Item 5 for 20-F)
- Risk Factors (Item 1A)
- Product-specific revenue commentary

Two-step process:
1. Use EDGAR submissions API to find the filing document URL
2. Fetch the filing HTML and extract relevant sections

Rate limit: SEC requires ≤10 req/sec and a descriptive User-Agent.
"""
import re
import os
import html as htmlmod
import logging
from typing import Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

SEC_USER_AGENT = os.environ.get(
    'SEC_EDGAR_USER_AGENT',
    'DataKinetic/1.0 research@datakinetic.com',
)
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"


@dataclass
class MDAExtraction:
    accession_number: str
    filing_type: str
    filing_date: str
    mda_text: str          # Truncated to 5000 chars
    risk_factors_text: str  # Truncated to 3000 chars
    product_mentions: list  # Product name → revenue context snippets


def _clean_html(raw: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = htmlmod.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_section(text: str, start_markers: list[str], end_markers: list[str], max_chars: int = 5000) -> str:
    """Extract a text section between start and end markers."""
    best_start = -1
    for marker in start_markers:
        idx = text.lower().find(marker.lower())
        if idx >= 0 and (best_start < 0 or idx < best_start):
            best_start = idx

    if best_start < 0:
        return ''

    # Find the end — next major section header
    search_from = best_start + 100  # skip past the header itself
    best_end = len(text)
    for marker in end_markers:
        idx = text.lower().find(marker.lower(), search_from)
        if idx >= 0 and idx < best_end:
            best_end = idx

    section = text[best_start:best_end].strip()
    return section[:max_chars]


def _extract_product_mentions(text: str, product_name: str, max_snippets: int = 5) -> list[dict]:
    """Find all mentions of a product with surrounding revenue context."""
    snippets = []
    pattern = re.compile(re.escape(product_name), re.IGNORECASE)

    for m in pattern.finditer(text):
        start = max(0, m.start() - 150)
        end = min(len(text), m.end() + 300)
        context = text[start:end].strip()

        # Only keep snippets that mention revenue/money
        if re.search(r'\$[\d,]+|revenue|sales|growth|million|billion|increased|decreased', context, re.IGNORECASE):
            snippets.append({
                'product': product_name,
                'context': context,
                'position': m.start(),
            })
            if len(snippets) >= max_snippets:
                break

    return snippets


async def get_filing_document_url(cik: str, filing_type: str = '20-F') -> Optional[tuple[str, str, str]]:
    """Find the primary filing document URL from EDGAR submissions API.

    Returns: (document_url, accession_number, filing_date) or None
    """
    cik_padded = cik.zfill(10)
    url = f"{SEC_SUBMISSIONS_URL}/CIK{cik_padded}.json"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers={'User-Agent': SEC_USER_AGENT})
        if resp.status_code != 200:
            logger.warning(f"EDGAR submissions API returned {resp.status_code} for CIK {cik}")
            return None

        data = resp.json()
        recent = data.get('filings', {}).get('recent', {})
        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])
        docs = recent.get('primaryDocument', [])

        for i in range(min(len(forms), 100)):
            if forms[i] == filing_type:
                acc_clean = accessions[i].replace('-', '')
                cik_num = cik.lstrip('0')
                doc_url = f"{SEC_ARCHIVES_URL}/{cik_num}/{acc_clean}/{docs[i]}"
                return doc_url, accessions[i], dates[i]

    return None


async def extract_mda_from_filing(
    cik: str,
    product_name: str,
    filing_type: str = '20-F',
) -> Optional[MDAExtraction]:
    """Fetch an SEC filing and extract MD&A, risk factors, and product mentions.

    Args:
        cik: SEC CIK number (e.g., '0000901832' for AstraZeneca)
        product_name: Product brand name to search for (e.g., 'Imfinzi')
        filing_type: '10-K' or '20-F'
    """
    try:
        result = await get_filing_document_url(cik, filing_type)
        if not result:
            logger.warning(f"No {filing_type} found for CIK {cik}")
            return None

        doc_url, accession, filing_date = result
        logger.info(f"Fetching {filing_type} from {doc_url}")

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(doc_url, headers={'User-Agent': SEC_USER_AGENT})
            if resp.status_code != 200:
                logger.warning(f"Filing fetch returned {resp.status_code}: {doc_url}")
                return None

            text = _clean_html(resp.text)

        # Extract MD&A section
        if filing_type == '20-F':
            mda_starts = ['Item 5', 'Operating and Financial Review', "Management's Discussion"]
            mda_ends = ['Item 6', 'Item 7', 'Directors, Senior Management']
        else:  # 10-K
            mda_starts = ['Item 7', "Management's Discussion and Analysis"]
            mda_ends = ['Item 7A', 'Item 8', 'Financial Statements']

        mda_text = _extract_section(text, mda_starts, mda_ends, max_chars=5000)

        # Extract Risk Factors
        risk_text = _extract_section(
            text,
            ['Item 1A', 'Risk Factors'],
            ['Item 1B', 'Item 2', 'Unresolved Staff Comments'],
            max_chars=3000,
        )

        # Extract product-specific mentions
        product_mentions = _extract_product_mentions(text, product_name)

        return MDAExtraction(
            accession_number=accession,
            filing_type=filing_type,
            filing_date=filing_date,
            mda_text=mda_text,
            risk_factors_text=risk_text,
            product_mentions=product_mentions,
        )

    except Exception as e:
        logger.error(f"MD&A extraction failed for CIK {cik}: {e}")
        return None
