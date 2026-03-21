"""SEC EDGAR MD&A Indication Revenue Parser
Feature: 003-molecule-assessment-dashboard

Parses MD&A text from SEC 10-K/20-F filings to extract per-indication revenue
mentions. Maps extracted indication names to ICD-10 codes via pattern matching.
Writes results to mol_silver.indication_revenue.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Revenue extraction patterns:
# Matches "$1.2B", "$450M", "$1,200M", "$3.5 billion" in context of indication names
REVENUE_PATTERN = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(billion|billion|B|million|million|M)\b',
    re.IGNORECASE,
)

# Common oncology + disease indication names for matching in MD&A text
INDICATION_PATTERNS = {
    'C34.9': [r'NSCLC', r'non[- ]?small[- ]?cell lung cancer', r'lung cancer'],
    'C67.9': [r'bladder cancer', r'urothelial', r'MIBC', r'muscle[- ]?invasive bladder'],
    'C50.9': [r'breast cancer', r'HER2[+-]?', r'triple[- ]?negative breast'],
    'C18.9': [r'colorectal cancer', r'CRC', r'colon cancer'],
    'C22.0': [r'hepatocellular', r'HCC', r'liver cancer'],
    'C25.9': [r'pancreatic cancer', r'PDAC'],
    'C61':   [r'prostate cancer', r'CRPC', r'mCRPC'],
    'C43.9': [r'melanoma'],
    'C64.9': [r'renal cell', r'RCC', r'kidney cancer'],
    'C71.9': [r'glioblastoma', r'GBM', r'brain cancer'],
    'C34.1': [r'SCLC', r'small[- ]?cell lung cancer'],
    'C56.9': [r'ovarian cancer'],
    'C16.9': [r'gastric cancer', r'stomach cancer', r'gastroesophageal'],
    'C73':   [r'thyroid cancer'],
    'C83.3': [r'DLBCL', r'diffuse large B[- ]?cell'],
    'C91.1': [r'CLL', r'chronic lymphocytic leukemia'],
    'C90.0': [r'multiple myeloma', r'myeloma'],
    # Non-oncology
    'J44.1': [r'COPD', r'chronic obstructive'],
    'J45.9': [r'asthma'],
    'M05.9': [r'rheumatoid arthritis', r'\bRA\b'],
    'L40.0': [r'psoriasis', r'psoriatic'],
    'K50.9': [r"Crohn", r'inflammatory bowel', r'\bIBD\b'],
    'G35':   [r'multiple sclerosis', r'\bMS\b'],
    'E11.9': [r'type 2 diabetes', r'T2DM', r'T2D\b'],
}


def _normalize_revenue(amount_str: str, unit: str) -> float:
    """Convert revenue string + unit to $M."""
    amount = float(amount_str.replace(',', ''))
    unit_lower = unit.lower()
    if unit_lower in ('b', 'billion'):
        return amount * 1000  # Convert to $M
    return amount  # Already in $M


def _find_indication_in_context(text_window: str) -> Optional[str]:
    """Search a text window for an indication name, return ICD-10 code if found."""
    for icd10, patterns in INDICATION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_window, re.IGNORECASE):
                return icd10
    return None


def parse_mda_for_indication_revenue(
    mda_text: str,
    product_name: str,
    data_year: int,
    source_filing: str,
    molecule_id: Optional[str] = None,
    total_product_revenue: Optional[float] = None,
) -> list[dict]:
    """Parse MD&A text and extract per-indication revenue data.

    Returns list of dicts ready for insertion into mol_silver.indication_revenue.
    """
    if not mda_text:
        return []

    results = []
    seen = set()

    for match in REVENUE_PATTERN.finditer(mda_text):
        amount_str = match.group(1)
        unit = match.group(2)
        revenue_usd = _normalize_revenue(amount_str, unit)

        # Look at surrounding context (200 chars before and after the revenue mention)
        start = max(0, match.start() - 200)
        end = min(len(mda_text), match.end() + 200)
        context_window = mda_text[start:end]

        icd10 = _find_indication_in_context(context_window)
        if not icd10:
            continue

        # Deduplicate: same indication + similar revenue in same filing
        dedup_key = (icd10, round(revenue_usd, 0))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        revenue_share = None
        if total_product_revenue and total_product_revenue > 0:
            revenue_share = round((revenue_usd / total_product_revenue) * 100, 2)

        results.append({
            'icd10_code': icd10,
            'molecule_id': molecule_id,
            'product_name': product_name,
            'indication_revenue_usd': revenue_usd,
            'total_product_revenue_usd': total_product_revenue,
            'indication_revenue_share': revenue_share,
            'data_year': data_year,
            'source_filing': source_filing,
            'source': 'sec_edgar',
        })

    logger.info(
        f"Parsed {len(results)} indication-revenue entries from {source_filing} "
        f"for {product_name}"
    )
    return results
