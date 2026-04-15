"""EMA Summary of Product Characteristics (SmPC) PDF Section Parser.

Feature: 006-claims-engine-data-gaps (Item 10, T052)

Parses EMA SmPC PDFs into structured section data matching the openFDA
drug label schema. SmPC documents follow a standardised section numbering
defined by EU Regulation (EC) No 726/2004, Annex I.

Section Mappings (SmPC number -> silver column name):
    4.1 -> indications_and_usage
    4.2 -> dosage_and_administration
    4.3 -> contraindications
    4.4 -> warnings_and_cautions
    4.5 -> drug_interactions
    4.6 -> pregnancy (also maps to nursing_mothers)
    4.7 -> use_in_specific_populations
    4.8 -> adverse_reactions
    4.9 -> overdosage
    5.1 -> pharmacodynamics
    5.2 -> pharmacokinetics
    5.3 -> nonclinical_toxicology

PDF download is stubbed — requires EMA website scraping or EPAR API
integration to retrieve the actual SmPC PDF URLs per product.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# SmPC section number -> (silver column name, human-readable label)
SECTION_MAPPINGS: Dict[str, Tuple[str, str]] = {
    "4.1": ("indications_and_usage", "Therapeutic indications"),
    "4.2": ("dosage_and_administration", "Posology and method of administration"),
    "4.3": ("contraindications", "Contraindications"),
    "4.4": ("warnings_and_cautions", "Special warnings and precautions for use"),
    "4.5": ("drug_interactions", "Interaction with other medicinal products"),
    "4.6": ("pregnancy", "Fertility, pregnancy and lactation"),
    "4.7": ("use_in_specific_populations", "Effects on ability to drive and use machines"),
    "4.8": ("adverse_reactions", "Undesirable effects"),
    "4.9": ("overdosage", "Overdose"),
    "5.1": ("pharmacodynamics", "Pharmacodynamic properties"),
    "5.2": ("pharmacokinetics", "Pharmacokinetic properties"),
    "5.3": ("nonclinical_toxicology", "Preclinical safety data"),
}

# Regex pattern to match SmPC section headers.
# Matches patterns like "4.1 Therapeutic indications", "4.1. Therapeutic indications",
# "4.1  THERAPEUTIC INDICATIONS", and handles leading whitespace.
# Section numbers are in the range 1-13 with optional sub-numbering.
_SECTION_HEADER_RE = re.compile(
    r"^\s*(\d{1,2}(?:\.\d{1,2})?)\s*\.?\s+(.+?)(?:\s*)$",
    re.MULTILINE,
)


def parse_smpc_text(text: str) -> Dict[str, str]:
    """Parse SmPC plain text into structured sections.

    Splits the text at section headers matching the EU SmPC format
    (e.g., "4.1 Therapeutic indications") and returns a dict keyed
    by the silver column name from SECTION_MAPPINGS.

    Args:
        text: Plain text extracted from an SmPC PDF.

    Returns:
        Dict mapping silver column names to section body text.
        Sections not found in the text are omitted.
    """
    if not text or not text.strip():
        return {}

    # Find all section header positions
    headers: List[Tuple[int, int, str, str]] = []
    for match in _SECTION_HEADER_RE.finditer(text):
        section_num = match.group(1).rstrip(".")
        section_title = match.group(2).strip()
        headers.append((match.start(), match.end(), section_num, section_title))

    if not headers:
        logger.warning("No SmPC section headers found in text (%d chars)", len(text))
        return {}

    # Extract section bodies (text between consecutive headers)
    sections: Dict[str, str] = {}
    for i, (start, end, section_num, section_title) in enumerate(headers):
        if section_num not in SECTION_MAPPINGS:
            continue

        col_name, _label = SECTION_MAPPINGS[section_num]

        # Body extends from end of this header to start of next header
        body_start = end
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()

        if body:
            sections[col_name] = body

    logger.info(
        "Parsed SmPC: %d/%d mapped sections found",
        len(sections), len(SECTION_MAPPINGS),
    )

    # Also extract pregnancy subsection into nursing_mothers if section 4.6 is present
    if "pregnancy" in sections:
        nursing_text = _extract_nursing_subsection(sections["pregnancy"])
        if nursing_text:
            sections["nursing_mothers"] = nursing_text

    return sections


def _extract_nursing_subsection(section_46_text: str) -> Optional[str]:
    """Extract the breast-feeding/lactation subsection from section 4.6.

    Section 4.6 ("Fertility, pregnancy and lactation") typically contains
    subsections for Pregnancy, Breast-feeding, and Fertility. This helper
    extracts the Breast-feeding content to map to the nursing_mothers column.

    Args:
        section_46_text: Full text of SmPC section 4.6.

    Returns:
        Extracted breast-feeding/lactation text, or None if not found.
    """
    # Match common subsection headers
    pattern = re.compile(
        r"(?:Breast-?feeding|Lactation)\s*\n(.*?)(?=\n(?:Fertility|Pregnancy|\d+\.\d+)|$)",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(section_46_text)
    if match:
        return match.group(1).strip() or None
    return None


def download_smpc_pdf(product_name: str, ema_number: Optional[str] = None) -> Optional[bytes]:
    """Download an SmPC PDF from EMA.

    STUB: This function is a placeholder for EMA SmPC PDF download.
    Actual implementation requires either:
      1. Scraping the EMA product page for the SmPC PDF link, or
      2. Using the EMA EPAR API (if/when available) to resolve the PDF URL.

    The EMA product page pattern is:
      https://www.ema.europa.eu/en/medicines/human/EPAR/<product-slug>

    Args:
        product_name: EMA product name (e.g., "dupixent").
        ema_number: Optional EMA procedure number (e.g., "EMEA/H/C/004390").

    Returns:
        PDF bytes, or None (stub always returns None).
    """
    logger.info(
        "SmPC PDF download stub called for product=%s ema_number=%s — "
        "not yet implemented. Use manual PDF extraction.",
        product_name, ema_number,
    )
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF.

    STUB: Requires a PDF library (e.g., pymupdf/fitz, pdfplumber).
    Returns empty string until dependency is added.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        Extracted plain text.
    """
    logger.warning(
        "PDF text extraction stub called — install pymupdf or pdfplumber "
        "and implement actual extraction."
    )
    return ""
