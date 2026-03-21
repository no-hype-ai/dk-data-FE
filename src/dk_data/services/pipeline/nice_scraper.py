"""NICE Guidance Scraper — extracts structured HTA decision data from NICE TA pages.

NICE Technology Appraisals have a consistent structure:
- Chapter 1: Recommendations (section 1.1 contains the decision)
- Published date in <time datetime="...">
- Guidance ID in breadcrumbs/URL (e.g., TA798)

Decision patterns:
- "is recommended" / "recommended as an option" → Recommended
- "is not recommended" → Not Recommended
- "can be used" / "only if" / "within its marketing authorisation" → Recommended (conditional)
- "recommended for use within the Cancer Drugs Fund" → Recommended (CDF)
- "terminated" → Terminated
"""
import re
import logging
from typing import Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

NICE_BASE = "https://www.nice.org.uk/guidance"


@dataclass
class NICEDecision:
    guidance_id: str
    title: str
    decision: str  # Recommended, Not recommended, Recommended (conditional), Recommended (CDF), Terminated
    decision_date: Optional[str]  # YYYY-MM-DD
    indication: Optional[str]
    recommendation_text: str  # Full 1.1 recommendation sentence
    url: str


def _clean_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def _classify_decision(recommendation_text: str) -> str:
    """Classify the NICE decision from the recommendation sentence."""
    lower = recommendation_text.lower()

    if 'is not recommended' in lower or 'are not recommended' in lower:
        return 'Not recommended'
    if 'cancer drugs fund' in lower or 'cdf' in lower:
        return 'Recommended (CDF)'
    if 'managed access' in lower:
        return 'Recommended (managed access)'
    if any(p in lower for p in [
        'is recommended', 'are recommended', 'recommended as an option',
        'recommended, within', 'recommended for use',
    ]):
        return 'Recommended'
    if 'can be used' in lower or 'should be used' in lower:
        return 'Recommended (conditional)'
    if 'terminated' in lower:
        return 'Terminated'

    return 'Unknown'


def _extract_indication(recommendation_text: str) -> Optional[str]:
    """Extract the indication from the NICE recommendation sentence."""
    # Patterns: "for treating X in adults", "as an option for X"
    patterns = [
        r'(?:for treating|for the treatment of|as an option for|for use in)\s+(.+?)(?:\s+in adults|\s+if|\s+only|\s+when|\.\s)',
        r'(?:for|treating)\s+((?:locally |advanced |unresectable |metastatic )*\w[\w\s\-]+(?:cancer|carcinoma|lymphoma|leukaemia|leukemia|melanoma|myeloma|sarcoma|glioma|mesothelioma))',
    ]
    for pat in patterns:
        m = re.search(pat, recommendation_text, re.IGNORECASE)
        if m:
            indication = m.group(1).strip()
            # Clean up trailing conjunctions/prepositions
            indication = re.sub(r'\s+(in|if|only|when|that|whose|after|following)$', '', indication, flags=re.IGNORECASE)
            return indication[:200]
    return None


async def scrape_nice_guidance(guidance_id: str) -> Optional[NICEDecision]:
    """Scrape a NICE guidance page for decision data.

    Args:
        guidance_id: e.g., 'ta798', 'ta944', 'ta1090'

    Returns:
        NICEDecision with structured fields, or None on failure.
    """
    url = f"{NICE_BASE}/{guidance_id}/chapter/1-Recommendations"

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"NICE {guidance_id}: HTTP {resp.status_code}")
                return None

            html = resp.text
            text = _clean_html(html)

            # Extract 1.1 recommendation sentence
            # The chapter page may only contain section 1 (recommendations)
            # so we grab everything after "1.1 " up to the next section marker or end
            rec_match = re.search(
                r'1\.1\s+(.{50,}?)(?:1\.2\s|\b2\s+[A-Z]|The committee|Evidence|Why the committee|$)',
                text,
                re.DOTALL,
            )
            if not rec_match:
                # Fallback: just grab everything after 1.1
                idx = text.find('1.1 ')
                if idx >= 0:
                    rec_text = text[idx + 4:idx + 504].strip()
                else:
                    logger.warning(f"NICE {guidance_id}: no 1.1 recommendation found")
                    return None
            else:
                rec_text = rec_match.group(1).strip()

            # Extract title from page
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            title = _clean_html(title_match.group(1)) if title_match else guidance_id

            # Extract publication date
            date_match = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', html)
            decision_date = date_match.group(1) if date_match else None

            # If no datetime attribute, try text pattern
            if not decision_date:
                date_text = re.search(r'Published.*?(\d{1,2}\s+\w+\s+\d{4})', text)
                if date_text:
                    from datetime import datetime
                    try:
                        dt = datetime.strptime(date_text.group(1), '%d %B %Y')
                        decision_date = dt.strftime('%Y-%m-%d')
                    except ValueError:
                        pass

            decision = _classify_decision(rec_text)
            indication = _extract_indication(rec_text)

            return NICEDecision(
                guidance_id=guidance_id.upper(),
                title=title,
                decision=decision,
                decision_date=decision_date,
                indication=indication,
                recommendation_text=rec_text[:500],
                url=f"{NICE_BASE}/{guidance_id}",
            )

    except Exception as e:
        logger.error(f"NICE {guidance_id} scrape failed: {e}")
        return None


async def scrape_nice_for_drug(drug_name: str, guidance_ids: list[str]) -> list[dict]:
    """Scrape multiple NICE guidance pages for a drug.

    Args:
        drug_name: Generic drug name (for context)
        guidance_ids: List of NICE guidance IDs (e.g., ['ta798', 'ta944'])

    Returns:
        List of dicts ready for insertion into mol_raw.hta_decisions response_body.
    """
    results = []
    for gid in guidance_ids:
        decision = await scrape_nice_guidance(gid)
        if decision:
            results.append({
                'agency': 'NICE',
                'guidance_id': decision.guidance_id,
                'drug_name': drug_name,
                'title': decision.title,
                'indication': decision.indication,
                'decision': decision.decision,
                'decision_date': decision.decision_date,
                'recommendation': decision.recommendation_text,
                'url': decision.url,
            })
            logger.info(
                f"NICE {decision.guidance_id}: {decision.decision} "
                f"({decision.indication}) published {decision.decision_date}"
            )
    return results
