"""
SEC EDGAR API Client.

Extract pharmaceutical product revenues from SEC 10-K/20-F filings.
FREE - US Government public data.

API Documentation: https://www.sec.gov/edgar/sec-api-documentation
Rate Limit: 10 requests per second (strictly enforced)

Data Extraction Strategy:
1. Use FilingSummary.xml to locate "Revenue by Product" report sections
2. Fetch specific report HTML (e.g., R138.htm for Pfizer)
3. Parse structured table data with [Member] product identifiers
4. Fall back to XBRL companyfacts API for aggregate data
"""

import os
import re
import html.parser
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .sec_rate_limiter import SECRateLimiter
from ...models.market_intelligence import Filing, ProductRevenue, PipelineAsset


class SECTableParser(html.parser.HTMLParser):
    """HTML parser for extracting table data from SEC filings."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row: List[str] = []
        self.rows: List[List[str]] = []
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_text = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr" and self.in_table:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = False
            self.current_row.append(self.current_text.strip())

    def handle_data(self, data):
        if self.in_cell:
            self.current_text += data


class SECEdgarClient(BaseAPIClient):
    """
    Extract pharmaceutical product revenues from SEC 10-K filings.
    FREE - US Government public data.
    """
    
    BASE_URL = "https://data.sec.gov"
    EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
    
    def __init__(self, config: Optional[APIClientConfig] = None):
        """Initialize SEC EDGAR client with rate limiting."""
        # SEC EDGAR requires User-Agent header with company contact email
        user_agent = os.getenv(
            "SEC_EDGAR_USER_AGENT",
            "DataKinetic Drug Intelligence Platform (contact@datakinetic.com)"
        )

        if config is None:
            config = APIClientConfig(
                base_url=self.BASE_URL,
                timeout=30.0,
                max_retries=3,
                cache_ttl=7 * 24 * 3600,  # 7 days (quarterly/annual filings)
                headers={
                    "User-Agent": user_agent,
                    "Accept": "application/json, text/html, */*",
                },
            )

        # Don't use cache manager in sync constructor - it requires async init
        # Caching will be handled at a higher level if needed
        super().__init__(config, cache_manager=None)

        # Store user agent and headers for direct httpx requests
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/json, text/html, */*",
        }

        # Override rate limiter: 10 requests per second (stricter than default)
        self.rate_limiter = SECRateLimiter(requests_per_second=10.0)
    
    async def health_check(self) -> bool:
        """Check if SEC EDGAR API is accessible."""
        try:
            # Simple health check - try to access the base URL
            client = await self._get_client()
            response = await client.get("/", timeout=5.0)
            return response.status_code < 500
        except Exception:
            return False
    
    async def get_company_filings(
        self,
        cik: str,
        filing_type: str = "10-K",
        years: int = 5
    ) -> List[Filing]:
        """
        Get recent 10-K/10-Q filings for a company.
        
        Args:
            cik: SEC Central Index Key (10-digit, zero-padded)
            filing_type: Form type ("10-K", "10-Q", "8-K")
            years: Number of years of filings to retrieve
            
        Returns:
            List of Filing objects
        """
        await self.rate_limiter.acquire()
        
        # Pad CIK to 10 digits
        cik_padded = cik.zfill(10)
        url = f"{self.BASE_URL}/submissions/CIK{cik_padded}.json"
        
        try:
            # Use base client's _get method (relative to base_url)
            endpoint = url.replace(self.BASE_URL, "")
            data = await super()._get(endpoint)
            
            filings = []
            recent = data.get('filings', {}).get('recent', {})
            
            forms = recent.get('form', [])
            accession_numbers = recent.get('accessionNumber', [])
            filing_dates = recent.get('filingDate', [])
            
            for i, form in enumerate(forms):
                if form == filing_type:
                    if i < len(accession_numbers) and i < len(filing_dates):
                        filing_date = datetime.strptime(filing_dates[i], "%Y-%m-%d").date()

                        # Use company CIK (not filer ID from accession) for URL construction
                        accession = accession_numbers[i]
                        accession_clean = accession.replace('-', '')

                        filings.append(Filing(
                            accession=accession,
                            filing_date=filing_date,
                            form=form,
                            document_url=f"{self.BASE_URL}/Archives/edgar/data/{cik}/{accession_clean}",
                            company_cik=cik,  # Store company CIK for reliable URL construction
                        ))
            
            # Sort by date descending and limit to requested years
            filings.sort(key=lambda x: x.filing_date, reverse=True)
            return filings[:years]
            
        except Exception as e:
            logger.error(f"Error fetching filings for CIK {cik}: {e}")
            return []
    
    def extract_mda_sections(self, filing_html: str) -> Dict[str, str]:
        """
        Extract MD&A and Risk Factors sections from 10-K/20-F filing HTML.

        Searches for section headers matching:
        - "Item 7" or "Management's Discussion and Analysis" (MD&A)
        - "Item 1A" or "Risk Factors"

        Extracts text between the section header and the next section,
        truncated to 5000 chars max for LLM context injection.

        Args:
            filing_html: Raw HTML content of the filing

        Returns:
            Dict with 'mda_text' and 'risk_factors_text' keys
        """
        result = {'mda_text': '', 'risk_factors_text': ''}

        if not filing_html:
            return result

        # Parse HTML to plain text
        full_text = BeautifulSoup(filing_html, 'html.parser').get_text()

        # Normalize whitespace runs (but preserve paragraph breaks)
        full_text = re.sub(r'[ \t]+', ' ', full_text)
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)

        # --- MD&A extraction ---
        # Item 7 (10-K) or "Management's Discussion and Analysis" (20-F uses Item 5)
        mda_start_patterns = [
            r'(?i)item\s*7[\.\s:]*\s*management.s\s+discussion\s+and\s+analysis',
            r'(?i)item\s*7[\.\s]*\s*management.s\s+discussion',
            r'(?i)item\s*7[\.\s:]+\s*md\s*&\s*a',
            r"(?i)management.s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition",
            r"(?i)management.s\s+discussion\s+and\s+analysis",
            r'(?i)item\s*5[\.\s:]*\s*operating\s+and\s+financial\s+review',  # 20-F
        ]
        # MD&A ends at Item 7A (Quantitative Disclosures) or Item 8 (Financial Statements)
        mda_end_patterns = [
            r'(?i)item\s*7a[\.\s:]*\s*quantitative\s+and\s+qualitative',
            r'(?i)item\s*8[\.\s:]*\s*financial\s+statements',
            r'(?i)item\s*6[\.\s:]*\s*directors',  # 20-F: Item 6 after Item 5
        ]

        mda_text = self._extract_section(full_text, mda_start_patterns, mda_end_patterns)
        if mda_text:
            result['mda_text'] = mda_text[:5000]

        # --- Risk Factors extraction ---
        risk_start_patterns = [
            r'(?i)item\s*1a[\.\s:]*\s*risk\s+factors',
            r'(?i)item\s*3[\.\s:]*\s*(?:key\s+information.*)?risk\s+factors',  # 20-F Item 3D
            r'(?i)risk\s+factors',
        ]
        risk_end_patterns = [
            r'(?i)item\s*1b[\.\s:]*\s*unresolved\s+staff\s+comments',
            r'(?i)item\s*2[\.\s:]*\s*(?:properties|description\s+of\s+property)',
            r'(?i)item\s*4[\.\s:]*\s*(?:information\s+on\s+the\s+company|mine\s+safety)',  # 20-F
        ]

        risk_text = self._extract_section(full_text, risk_start_patterns, risk_end_patterns)
        if risk_text:
            result['risk_factors_text'] = risk_text[:5000]

        return result

    def _extract_section(
        self,
        full_text: str,
        start_patterns: List[str],
        end_patterns: List[str]
    ) -> Optional[str]:
        """
        Extract a section of text between start and end patterns.

        Finds the first matching start pattern, then the first matching end pattern
        after it, and returns the text between them.
        """
        start_idx = None
        for pattern in start_patterns:
            match = re.search(pattern, full_text)
            if match:
                start_idx = match.start()
                break

        if start_idx is None:
            return None

        # Search for end marker after the start (skip ahead to avoid matching
        # a table-of-contents reference right at the start)
        search_from = start_idx + 100
        end_idx = None
        for pattern in end_patterns:
            match = re.search(pattern, full_text[search_from:])
            if match:
                candidate = search_from + match.start()
                if end_idx is None or candidate < end_idx:
                    end_idx = candidate

        if end_idx is None:
            # No end marker found; take up to 10000 chars from start
            end_idx = min(start_idx + 10000, len(full_text))

        section = full_text[start_idx:end_idx].strip()

        # Only return if we got meaningful content (not just a header reference)
        if len(section) > 200:
            return section

        return None

    async def extract_product_revenues(
        self,
        cik: str,
        years: List[int]
    ) -> List[ProductRevenue]:
        """
        Parse 10-K/20-F filings to extract product-level revenue.

        Strategy (optimized based on SEC filing structure analysis):
        1. Fetch FilingSummary.xml to locate specific revenue reports
        2. Find "Revenue by Product" or "Net Sales by Segment" reports
        3. Fetch and parse the specific report HTML (e.g., R138.htm)
        4. Extract product names from [Member] tags and associated values
        5. Fall back to main document HTML parsing if needed

        Also extracts MD&A and Risk Factors sections from the filing HTML.

        Args:
            cik: SEC Central Index Key
            years: List of years to extract (e.g., [2024, 2023, 2022])

        Returns:
            List of ProductRevenue objects
        """
        # Try 10-K (domestic) first, then 20-F (foreign private issuers)
        filings = await self.get_company_filings(cik, filing_type="10-K", years=len(years))
        is_foreign = False

        if not filings:
            # Try 20-F for foreign companies (e.g., Sanofi, Novartis, AstraZeneca)
            filings = await self.get_company_filings(cik, filing_type="20-F", years=len(years))
            is_foreign = True
            logger.info(f"Using 20-F filings for CIK {cik} (foreign issuer)")

        revenues = []

        for filing in filings:
            try:
                # Strategy 1: Try FilingSummary.xml + specific revenue report (most reliable)
                product_revenues = await self._extract_from_filing_summary(filing, is_foreign)
                if product_revenues:
                    revenues.extend(product_revenues)
                    logger.info(f"Extracted {len(product_revenues)} products from FilingSummary for {filing.accession}")

                    # Also extract MD&A sections from the main filing HTML
                    html_content = await self._fetch_10k_html(filing)
                    if html_content:
                        mda_sections = self.extract_mda_sections(html_content)
                        # Attach MD&A text to each revenue record from this filing
                        for rev in product_revenues:
                            rev.mda_text = mda_sections.get('mda_text', '')
                            rev.risk_factors_text = mda_sections.get('risk_factors_text', '')
                    continue

                # Strategy 2: Fall back to main document HTML parsing
                html_content = await self._fetch_10k_html(filing)
                if html_content:
                    # Extract MD&A sections
                    mda_sections = self.extract_mda_sections(html_content)

                    product_revenues = self._parse_html_revenue_tables(
                        html_content,
                        filing.accession,
                        filing.filing_date.year
                    )
                    # Attach MD&A text to each revenue record
                    for rev in product_revenues:
                        rev.mda_text = mda_sections.get('mda_text', '')
                        rev.risk_factors_text = mda_sections.get('risk_factors_text', '')
                    revenues.extend(product_revenues)
            except Exception as e:
                logger.warning(f"Error extracting revenues from filing {filing.accession}: {e}")
                continue

        return revenues

    # SEC Archives URL - use www.sec.gov for Archives (data.sec.gov returns 404 for some paths)
    ARCHIVES_URL = "https://www.sec.gov"

    async def _extract_from_filing_summary(
        self,
        filing: Filing,
        is_foreign: bool = False
    ) -> List[ProductRevenue]:
        """
        Extract product revenues using FilingSummary.xml structure.

        This is the most reliable method as it uses SEC's structured reports.
        """
        # Get CIK and accession for URL construction
        cik = self._extract_cik_from_filing(filing)
        accession_clean = filing.accession.replace('-', '')

        # Fetch FilingSummary.xml from www.sec.gov (more reliable than data.sec.gov for Archives)
        summary_url = f"{self.ARCHIVES_URL}/Archives/edgar/data/{cik}/{accession_clean}/FilingSummary.xml"

        try:
            await self.rate_limiter.acquire()
            client = await self._get_client()
            response = await client.get(summary_url, headers=self.headers)

            if response.status_code != 200:
                logger.debug(f"FilingSummary.xml not found for {filing.accession}")
                return []

            # Parse XML to find revenue reports
            root = ET.fromstring(response.text)
            revenue_reports = self._find_revenue_reports(root, is_foreign)

            if not revenue_reports:
                logger.debug(f"No revenue reports found in FilingSummary for {filing.accession}")
                return []

            # Fetch and parse the revenue reports
            all_revenues = []
            for report_name, report_file in revenue_reports:
                report_url = f"{self.ARCHIVES_URL}/Archives/edgar/data/{cik}/{accession_clean}/{report_file}"

                await self.rate_limiter.acquire()
                report_response = await client.get(report_url, headers=self.headers)

                if report_response.status_code == 200:
                    revenues = self._parse_structured_revenue_report(
                        report_response.text,
                        filing.accession,
                        filing.filing_date.year,
                        is_foreign
                    )
                    all_revenues.extend(revenues)
                    logger.debug(f"Extracted {len(revenues)} revenues from {report_file}")

            return all_revenues

        except Exception as e:
            logger.warning(f"Error extracting from FilingSummary: {e}")
            return []

    def _find_revenue_reports(
        self,
        root: ET.Element,
        is_foreign: bool = False
    ) -> List[Tuple[str, str]]:
        """
        Find revenue-related reports in FilingSummary.xml.

        Returns list of (report_name, html_file) tuples.
        """
        revenue_reports = []

        # Keywords indicating revenue/product reports
        # 10-K uses "Revenue by Product", 20-F uses "Net Sales by Segment"
        # Merck uses "Sales of Company's Products"
        revenue_keywords = [
            'revenues by product',
            'revenue by product',
            'net sales by segment',
            'net sales by product',
            'segment information - summary of net sales',
            'product revenue',
            'sales by product',
            "sales of company's products",  # Merck style
            'disaggregation of revenue by product',  # BMS style
        ]

        # Find all Report elements
        for report in root.findall('.//Report'):
            long_name = report.find('LongName')
            html_file = report.find('HtmlFileName')

            if long_name is not None and html_file is not None:
                name = (long_name.text or '').lower()
                file_name = html_file.text

                # Check if this is a revenue report
                if any(kw in name for kw in revenue_keywords):
                    # Prefer "(Detail)" reports over "(Tables)" for actual values
                    if 'detail' in name.lower() and file_name:
                        revenue_reports.append((long_name.text, file_name))
                    elif 'table' not in name.lower() and file_name:
                        # Also include non-table reports
                        revenue_reports.append((long_name.text, file_name))

        # Sort to prioritize "Detail" reports
        revenue_reports.sort(key=lambda x: 'detail' in x[0].lower(), reverse=True)

        return revenue_reports[:3]  # Limit to top 3 most relevant

    def _parse_structured_revenue_report(
        self,
        html_content: str,
        source_filing: str,
        year: int,
        is_foreign: bool = False
    ) -> List[ProductRevenue]:
        """
        Parse a structured revenue report HTML (e.g., R138.htm for Pfizer, R59.htm for BMS).

        Supports two formats:
        1. Pfizer/Sanofi style with [Member] tags:
           - Row with product [Member] identifier
           - "Revenue from External Customer [Line Items]" row (skip)
           - "Revenues:" row with actual values

        2. BMS style without [Member] tags:
           - Row with product name only (e.g., "Opdivo")
           - "Revenue from External Customer [Line Items]" row (skip)
           - "Total Revenues" row with actual values
        """
        parser = SECTableParser()
        parser.feed(html_content)

        revenues = []
        rows = parser.rows

        # Detect currency from header (EUR for foreign like Sanofi, USD for domestic)
        currency_multiplier = 1.0
        for row in rows[:3]:
            row_text = ' '.join(row).lower()
            if 'eur' in row_text:
                # EUR values - will need FX conversion (approximate)
                currency_multiplier = 1.10  # Approximate EUR/USD rate
                logger.debug("Detected EUR currency, applying conversion")
                break

        # Common pharma drug names to help identify product rows
        pharma_keywords = [
            'opdivo', 'eliquis', 'revlimid', 'pomalyst', 'orencia', 'sprycel',
            'yervoy', 'reblozyl', 'opdualag', 'camzyos', 'sotyktu', 'breyanzi',
            'abecma', 'zeposia', 'inrebic', 'onureg', 'krazati', 'augtyro',
            'dupixent', 'prevnar', 'ibrance', 'paxlovid', 'comirnaty', 'keytruda',
            'humira', 'skyrizi', 'rinvoq', 'stelara', 'imbruvica', 'entresto'
        ]

        # Skip keywords - rows that shouldn't be treated as products
        skip_keywords = [
            'total revenues', 'total', 'united states', 'international', 'other',
            'growth portfolio', 'legacy portfolio', 'revenue from external',
            'line items', 'performance obligation', 'segment', 'region'
        ]

        i = 0
        while i < len(rows) - 2:
            row = rows[i]
            if not row:
                i += 1
                continue

            first_cell = row[0] if row else ""
            first_cell_lower = first_cell.lower().strip()

            # Skip empty cells
            if not first_cell_lower:
                i += 1
                continue

            product_name = None

            # Strategy 1: Look for product [Member] rows (Pfizer/Sanofi style)
            if '[Member]' in first_cell and '|' in first_cell:
                # Skip division-level aggregates
                if 'Division' in first_cell or 'Total' in first_cell:
                    i += 1
                    continue
                product_name = self._extract_product_name_from_member(first_cell)

            # Strategy 2: Look for Merck-style format (Operating Segments | Segment | Product)
            # Format: "Operating Segments | Pharmaceutical | Keytruda" without [Member] tags
            # Must check BEFORE skip_keywords since it contains 'segment'
            elif '|' in first_cell and 'Operating Segments' in first_cell:
                parts = [p.strip() for p in first_cell.split('|')]
                if len(parts) >= 3:
                    # Last part is usually the product name
                    potential_product = parts[-1]
                    # Check if it's a known pharma product or reasonable name
                    if (potential_product.lower() in pharma_keywords or
                        (len(potential_product) > 3 and len(potential_product) < 30 and
                         potential_product[0].isupper() and
                         not any(skip in potential_product.lower() for skip in skip_keywords))):
                        product_name = potential_product

            # Strategy 3: Look for standalone product names (BMS style)
            # A product row typically has just a name in the first cell with empty other cells
            elif (len(row) >= 2 and
                  not any(row[1:4]) and  # Other cells are empty
                  len(first_cell) < 50 and  # Reasonable name length
                  first_cell[0].isupper()):  # Starts with capital

                # Check if this looks like a drug name
                if (any(kw in first_cell_lower for kw in pharma_keywords) or
                    (len(first_cell) > 3 and len(first_cell) < 30)):
                    product_name = first_cell.strip()

            if product_name:
                # Look for revenue values in subsequent rows
                for j in range(i + 1, min(i + 4, len(rows))):
                    value_row = rows[j]
                    if not value_row:
                        continue

                    value_row_text = str(value_row[0]).lower().strip()
                    # Match: "revenues", "net sales", "sales" (exact match for Merck)
                    if ('revenues' in value_row_text or 'net sales' in value_row_text or
                        value_row_text == 'sales'):
                        # Extract numeric values from columns 1-4
                        revenue_values = self._extract_revenue_values(value_row[1:5])

                        if revenue_values:
                            # First value is typically current year
                            revenue_2024 = revenue_values[0] if revenue_values else None
                            revenue_2023 = revenue_values[1] if len(revenue_values) > 1 else None

                            if revenue_2024 and revenue_2024 > 50:  # Min $50M threshold
                                # Calculate YoY growth
                                yoy_growth = None
                                if revenue_2023 and revenue_2023 > 0:
                                    yoy_growth = (revenue_2024 - revenue_2023) / revenue_2023

                                revenues.append(ProductRevenue(
                                    product_name=product_name,
                                    revenue_usd=revenue_2024 * currency_multiplier,
                                    period="annual",
                                    year=year,
                                    source_filing=source_filing,
                                    yoy_growth=yoy_growth
                                ))
                        break
            i += 1

        # Deduplicate by product name (keep first occurrence, which is usually most specific)
        seen = set()
        unique_revenues = []
        for rev in revenues:
            key = rev.product_name.lower()
            if key not in seen:
                seen.add(key)
                unique_revenues.append(rev)

        return unique_revenues

    def _extract_product_name_from_member(self, cell_text: str) -> Optional[str]:
        """
        Extract product name from SEC [Member] cell format.

        Examples:
        - "Primary Care [Member] | Eliquis [Member] | Biopharma [Member]" -> "Eliquis"
        - "Biopharma [Member] | Dupixent [Member]" -> "Dupixent"
        - "Oncology [Member] | Ibrance [Member] | Biopharma [Member]" -> "Ibrance"
        """
        parts = cell_text.split('|')

        # Find the actual product (not segment/division)
        segment_keywords = [
            'biopharma', 'primary care', 'specialty care', 'oncology',
            'vaccines', 'consumer', 'hospital', 'operating segment',
            'u.s.', 'international', 'commercial', 'division'
        ]

        for part in parts:
            part = part.strip()
            if '[Member]' in part:
                # Extract name before [Member]
                name = part.replace('[Member]', '').strip()
                name_lower = name.lower()

                # Check if this is a segment or actual product
                if not any(kw in name_lower for kw in segment_keywords):
                    # This looks like a product name
                    return name

        return None

    def _extract_revenue_values(self, cells: List[str]) -> List[float]:
        """Extract numeric revenue values from table cells."""
        values = []

        for cell in cells:
            if not cell:
                continue

            # Clean the cell text
            cell_clean = cell.replace('$', '').replace(',', '').replace('€', '').strip()

            # Remove footnote markers like [1], [2], etc.
            cell_clean = re.sub(r'\[\d+\]', '', cell_clean).strip()

            # Handle parentheses for negative numbers
            cell_clean = cell_clean.replace('(', '-').replace(')', '')

            if cell_clean:
                try:
                    value = float(cell_clean)
                    values.append(value)
                except ValueError:
                    pass

        return values

    def _extract_cik_from_filing(self, filing: Filing) -> str:
        """Extract CIK from filing for URL construction (without leading zeros for Archives path)."""
        # Use company_cik if available (most reliable)
        if filing.company_cik:
            return filing.company_cik.lstrip('0') or '0'

        # Fall back to document_url parsing
        if filing.document_url:
            parts = filing.document_url.split('/Archives/edgar/data/')
            if len(parts) > 1:
                # Strip leading zeros from CIK
                return parts[1].split('/')[0].lstrip('0') or '0'

        # Last resort: accession number parsing (unreliable - filer ID, not company CIK)
        cik = filing.accession.split('-')[0]
        return cik.lstrip('0') or '0'
    
    async def get_pipeline_disclosures(
        self,
        cik: str
    ) -> List[PipelineAsset]:
        """
        Extract pipeline assets from 10-K Business section.
        
        Parses Item 1 (Business Description) for:
        - Development stage compounds
        - Phase information
        - Target indications
        - Partnership details
        
        Args:
            cik: SEC Central Index Key
            
        Returns:
            List of PipelineAsset objects
        """
        latest_10k = await self.get_company_filings(cik, filing_type="10-K", years=1)
        if not latest_10k:
            return []
        
        try:
            content = await self._fetch_item1_business(latest_10k[0])
            return self._extract_pipeline_assets(content, latest_10k[0].accession)
        except Exception as e:
            logger.error(f"Error extracting pipeline disclosures for CIK {cik}: {e}")
            return []
    
    def _parse_html_revenue_tables(
        self,
        html: str,
        source_filing: str,
        year: int
    ) -> List[ProductRevenue]:
        """
        Extract product revenues from HTML tables.

        Common patterns in pharma 10-Ks:
        - "Revenues by Product"
        - "Net Sales by Product"
        - "Product Revenue Summary"
        - "Selected Product Revenue"
        - Revenue breakdown tables near "MD&A" section
        """
        soup = BeautifulSoup(html, 'html.parser')
        revenues = []

        # Common pharma drug names to help identify revenue tables
        pharma_keywords = [
            'humira', 'keytruda', 'eliquis', 'revlimid', 'opdivo', 'eylea',
            'stelara', 'imbruvica', 'xarelto', 'paxlovid', 'comirnaty',
            'prevnar', 'ibrance', 'skyrizi', 'rinvoq', 'dupixent', 'jardiance',
            'ozempic', 'trulicity', 'mounjaro', 'wegovy', 'kisqali', 'kisunla',
            'aduhelm', 'leqembi', 'repatha', 'praluent', 'cosentyx', 'entresto',
            # AstraZeneca
            'tagrisso', 'imfinzi', 'lynparza', 'calquence', 'enhertu', 'farxiga',
            'brilinta', 'lokelma', 'zoladex', 'faslodex', 'breztri', 'saphnelo',
            'tezspire', 'soliris', 'ultomiris', 'symbicort', 'nexium', 'pulmicort',
            # Roche
            'tecentriq', 'avastin', 'herceptin', 'rituxan', 'ocrevus', 'perjeta',
            # Merck
            'januvia', 'gardasil', 'lagevrio', 'vaxneuvance', 'welireg',
            # Novartis
            'kisqali', 'pluvicto', 'kesimpta', 'leqvio', 'jakavi', 'tasigna'
        ]

        # Keywords that indicate revenue tables
        revenue_indicators = [
            'net sales', 'product revenue', 'revenue by product',
            'revenues by major product', 'selected product',
            'revenues by therapeutic', 'revenues by business segment',
            'worldwide revenue', 'product sales', 'net revenue'
        ]

        # Find all tables
        tables = soup.find_all('table')
        logger.info(f"Found {len(tables)} tables in 10-K filing")

        candidate_tables = []

        for table in tables:
            table_text = table.get_text().lower()

            # Check if table contains revenue indicators
            has_indicator = any(phrase in table_text for phrase in revenue_indicators)

            # Check if table contains pharma drug names
            drug_mentions = sum(1 for drug in pharma_keywords if drug in table_text)

            # Check if table contains dollar amounts
            has_dollars = '$' in table_text or 'million' in table_text or 'billion' in table_text

            if (has_indicator or drug_mentions >= 2) and has_dollars:
                candidate_tables.append((table, drug_mentions))

        # Sort by number of drug mentions (more drugs = likely revenue table)
        candidate_tables.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"Found {len(candidate_tables)} candidate revenue tables")

        for table, _ in candidate_tables[:5]:  # Process top 5 candidate tables
            rows = table.find_all('tr')

            # Try to identify header row
            header_row = None
            for row in rows[:3]:  # Check first 3 rows for header
                cells = row.find_all(['th', 'td'])
                cell_texts = [c.get_text().strip().lower() for c in cells]
                if any('year' in t or '2024' in t or '2023' in t or '2022' in t for t in cell_texts):
                    header_row = row
                    break

            # Parse data rows
            data_rows = rows[1:] if not header_row else rows[rows.index(header_row) + 1:]

            for row in data_rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue

                # First cell is usually product name — strip zero-width spaces and clean
                product_name = cells[0].get_text().strip()
                product_name = product_name.replace('\u200b', '').replace('\xa0', ' ').strip()

                # Clean up product name
                product_name = ' '.join(product_name.split())  # Normalize whitespace
                # Remove footnote markers like "1", "2" etc. at end of drug names
                product_name = re.sub(r'\d+$', '', product_name).strip()

                # Skip rows that are clearly not products
                skip_keywords = ['total', 'subtotal', 'other', 'revenue', 'net sales',
                               'year ended', 'three months', 'nine months', 'note',
                               'product sales', 'collaboration', 'alliance']
                if any(kw in product_name.lower() for kw in skip_keywords) and len(product_name) < 30:
                    continue

                # Look for numeric values in subsequent cells (skip separator cells)
                for cell in cells[1:8]:  # Check more cells — AZ 20-F has separator columns
                    revenue_text = cell.get_text().replace('\u200b', '').replace('\xa0', '').strip()
                    if not revenue_text or revenue_text in ('—', '-', 'n/m', 'n/a'):
                        continue
                    revenue_value = self._parse_revenue_value(revenue_text)

                    if revenue_value and revenue_value > 10:  # Filter out tiny values
                        # Check if this looks like a drug name
                        is_likely_drug = (
                            any(drug in product_name.lower() for drug in pharma_keywords) or
                            (len(product_name) > 3 and len(product_name) < 50 and
                             product_name[0].isupper())
                        )

                        if is_likely_drug or product_name:
                            revenues.append(ProductRevenue(
                                product_name=product_name,
                                revenue_usd=revenue_value,
                                period="annual",
                                year=year,
                                source_filing=source_filing
                            ))
                        break  # Only take first valid revenue per row

        # Deduplicate by product name (keep highest revenue)
        seen = {}
        for rev in revenues:
            key = rev.product_name.lower()
            if key not in seen or rev.revenue_usd > seen[key].revenue_usd:
                seen[key] = rev

        unique_revenues = list(seen.values())
        logger.info(f"Extracted {len(unique_revenues)} unique product revenues from 10-K")

        return unique_revenues
    
    def _parse_xbrl_revenues(
        self,
        xbrl_data: Dict[str, Any],
        source_filing: str
    ) -> List[ProductRevenue]:
        """
        Parse product revenues from XBRL structured data.
        
        Looks for standard XBRL tags:
        - us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
        - dei:DocumentPeriodEndDate
        - Custom product revenue tags (company-specific)
        """
        revenues = []
        
        try:
            # XBRL data structure: facts, contexts, units
            facts = xbrl_data.get('facts', {})
            contexts = xbrl_data.get('contexts', {})
            
            # Look for revenue facts
            # Common patterns: product revenue tags often contain "Product", "Revenue", "Sales"
            for concept_id, fact_list in facts.items():
                concept_lower = concept_id.lower()
                
                # Check if this looks like a product revenue concept
                if any(keyword in concept_lower for keyword in ['product', 'revenue', 'sales', 'net']):
                    for fact in fact_list:
                        if isinstance(fact, dict):
                            value = fact.get('value')
                            context_id = fact.get('contextId')
                            fact.get('unitId', 'USD')
                            
                            if value and context_id:
                                # Get context to extract period
                                context = contexts.get(context_id, {})
                                period = context.get('period', {})
                                
                                # Extract year
                                end_date = period.get('endDate')
                                year = None
                                if end_date:
                                    try:
                                        from datetime import datetime
                                        year = datetime.fromisoformat(end_date.replace('Z', '')).year
                                    except Exception:
                                        pass
                                
                                # Try to extract product name from concept ID or label
                                product_name = concept_id
                                labels = xbrl_data.get('labels', {})
                                if concept_id in labels:
                                    label = labels[concept_id].get('label', concept_id)
                                    # Try to extract product name from label
                                    # E.g., "Product Revenue - Humira" -> "Humira"
                                    if ' - ' in label:
                                        product_name = label.split(' - ')[-1].strip()
                                    elif 'Product' in label:
                                        # Try to extract product name
                                        parts = label.replace('Product', '').replace('Revenue', '').strip()
                                        if parts:
                                            product_name = parts
                                
                                # Parse value (handle millions/billions)
                                revenue_value = self._parse_revenue_value(str(value))
                                
                                if revenue_value and product_name:
                                    revenues.append(ProductRevenue(
                                        product_name=product_name,
                                        revenue_usd=revenue_value,
                                        period="annual" if not period.get('startDate') else "quarterly",
                                        year=year,
                                        source_filing=source_filing
                                    ))
            
            logger.info(f"Parsed {len(revenues)} product revenues from XBRL")
            return revenues
            
        except Exception as e:
            logger.warning(f"Error parsing XBRL revenues: {e}")
            return []
    
    def _parse_revenue_value(self, revenue_text: str) -> Optional[float]:
        """
        Parse revenue value from text string.

        Handles formats like:
        - "$1,234.5 million"
        - "$1.2 billion"
        - "1,234.5"
        """
        import re

        # Remove commas and $ signs
        text = revenue_text.replace(',', '').replace('$', '').replace('€', '').strip().lower()

        # Skip empty or placeholder values (".", "—", "-", "n/a")
        if not text or text in ('.', '—', '-', 'n/a', 'nil', '–'):
            return None

        # Extract number (must contain at least one digit)
        match = re.search(r'(\d[\d.]*)', text)
        if not match:
            return None

        try:
            value = float(match.group(1))
        except ValueError:
            return None
        
        # Handle explicit units (millions, billions)
        # SEC filings typically report values in millions USD unless stated otherwise
        if 'billion' in text:
            value *= 1000  # Convert billions to millions
        elif 'million' in text:
            pass  # Already in millions
        # No implicit scaling — SEC table values are in the unit stated in the
        # table header (usually "$m" or "in millions"). Guessing units causes
        # 100x errors (e.g., $261M → $261,000M).
        
        return value
    
    async def _fetch_xbrl(self, filing: Filing) -> Optional[Dict[str, Any]]:
        """Fetch XBRL company facts for the filing's company via the SEC API."""
        cik = filing.company_cik or self._extract_cik_from_filing(filing)
        cik_padded = cik.zfill(10)

        await self.rate_limiter.acquire()
        url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik_padded}.json"

        try:
            client = await self._get_client()
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.debug(f"XBRL companyfacts not available for CIK {cik_padded}: HTTP {response.status_code}")
                return None
            data = response.json()
            return data.get("facts")
        except Exception as e:
            logger.warning(f"Error fetching XBRL for CIK {cik_padded}: {e}")
            return None

    async def _get_filing_documents(self, filing: Filing) -> Optional[List[Dict[str, Any]]]:
        """Fetch the filing index to get list of documents."""
        await self.rate_limiter.acquire()

        # Get CIK without leading zeros for Archives path
        cik = self._extract_cik_from_filing(filing)
        accession_clean = filing.accession.replace('-', '')
        index_url = f"{self.ARCHIVES_URL}/Archives/edgar/data/{cik}/{accession_clean}/index.json"

        try:
            client = await self._get_client()
            response = await client.get(index_url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data.get('directory', {}).get('item', [])
        except Exception as e:
            logger.warning(f"Error fetching filing index for {filing.accession}: {e}")
            return None

    async def _fetch_10k_html(self, filing: Filing) -> Optional[str]:
        """Fetch HTML content of 10-K filing."""
        # First, get the list of documents to find the primary 10-K document
        documents = await self._get_filing_documents(filing)

        primary_doc = None
        if documents:
            # Look for the primary 10-K document (usually ends with .htm and contains "10k")
            # Exclude exhibits (exhNNN, ex-NNN patterns)
            for doc in documents:
                name = doc.get('name', '').lower()
                if name.endswith('.htm') or name.endswith('.html'):
                    if ('10k' in name or '10-k' in name) and 'ex' not in name:
                        primary_doc = doc.get('name')
                        break

            # Fallback: look for any .htm document that's large (likely the main filing)
            if not primary_doc:
                htm_docs = [d for d in documents if d.get('name', '').lower().endswith(('.htm', '.html'))]
                if htm_docs:
                    # Sort by size descending (largest is usually the main document)
                    def safe_size(doc):
                        try:
                            return int(str(doc.get('size', '0')).replace(',', ''))
                        except (ValueError, TypeError):
                            return 0
                    htm_docs.sort(key=safe_size, reverse=True)
                    primary_doc = htm_docs[0].get('name')

        if not primary_doc:
            primary_doc = filing.primary_document or 'index.html'

        await self.rate_limiter.acquire()

        # Get CIK without leading zeros for Archives path
        cik = self._extract_cik_from_filing(filing)
        accession_clean = filing.accession.replace('-', '')
        url = f"{self.ARCHIVES_URL}/Archives/edgar/data/{cik}/{accession_clean}/{primary_doc}"

        try:
            client = await self._get_client()
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            logger.info(f"Successfully fetched 10-K HTML from {url} ({len(response.text)} bytes)")
            return response.text
        except Exception as e:
            logger.error(f"Error fetching HTML for {filing.accession}: {e}")
            return None
    
    async def _fetch_item1_business(self, filing: Filing) -> str:
        """Fetch Item 1 (Business Description) section from 10-K.

        Extracts text between 'Item 1. Business' and 'Item 1A. Risk Factors'.
        Falls back to full document text if section markers are not found.
        """
        html = await self._fetch_10k_html(filing)
        if not html:
            return ""

        full_text = BeautifulSoup(html, 'html.parser').get_text()

        # Try to find Item 1 boundaries
        item1_patterns = [
            r'(?i)item\s*1[\.\s]*\s*business',
            r'(?i)ITEM\s+1[\.\s]+BUSINESS',
        ]
        item1a_patterns = [
            r'(?i)item\s*1a[\.\s]*\s*risk\s*factors',
            r'(?i)ITEM\s+1A[\.\s]+RISK\s+FACTORS',
        ]

        start_idx = None
        for pattern in item1_patterns:
            match = re.search(pattern, full_text)
            if match:
                start_idx = match.start()
                break

        end_idx = None
        if start_idx is not None:
            # Search for Item 1A after Item 1
            for pattern in item1a_patterns:
                match = re.search(pattern, full_text[start_idx + 50:])
                if match:
                    end_idx = start_idx + 50 + match.start()
                    break

        if start_idx is not None and end_idx is not None:
            section = full_text[start_idx:end_idx].strip()
            if len(section) > 200:
                logger.info(f"Extracted Item 1 Business section ({len(section)} chars)")
                return section

        # Fallback: return full text
        logger.debug("Item 1 markers not found, returning full document text")
        return full_text
    
    def _extract_pipeline_assets(
        self,
        content: str,
        source_filing: str
    ) -> List[PipelineAsset]:
        """Extract pipeline assets from Item 1 Business section text.

        Uses regex-based extraction to find compounds with phase information,
        indications, and partnership details.
        """
        if not content or len(content) < 100:
            return []

        assets: Dict[str, PipelineAsset] = {}

        # Phase patterns (order matters — more specific first)
        phase_patterns = [
            (r'(?i)\b(BLA|NDA)\b', 'NDA/BLA', 0.90),
            (r'(?i)\bPhase\s*(?:III|3)\b', 'Phase 3', 0.85),
            (r'(?i)\bPhase\s*(?:II(?:I|b|a)?|2(?:b|a)?)\b', 'Phase 2', 0.80),
            (r'(?i)\bPhase\s*(?:I(?:b|a)?|1(?:b|a)?)\b', 'Phase 1', 0.75),
            (r'(?i)\bpre[- ]?clinical\b', 'Pre-clinical', 0.65),
            (r'(?i)\binvestigational\b', 'Investigational', 0.60),
        ]

        # Common disease/indication keywords
        indication_patterns = [
            r'(?i)\b(?:for\s+(?:the\s+)?treatment\s+of)\s+([A-Za-z\s\-]+?)(?:\.|,|\band\b)',
            r'(?i)\b(?:indicated\s+for)\s+([A-Za-z\s\-]+?)(?:\.|,)',
            r'(?i)\b(?:in\s+patients?\s+with)\s+([A-Za-z\s\-]+?)(?:\.|,)',
        ]

        # Split into sentences for context-aware extraction
        sentences = re.split(r'(?<=[.!?])\s+', content)

        for sentence in sentences:
            for phase_re, phase_label, base_confidence in phase_patterns:
                if not re.search(phase_re, sentence):
                    continue

                # Look for compound names: capitalized words or codes (e.g., BMS-986165, ABT-199)
                compound_matches = re.findall(
                    r'\b([A-Z][A-Z0-9]+-?\d+(?:-\d+)?)\b'       # codes like BMS-986165
                    r'|\b([A-Z][a-z]{2,}(?:mab|nib|lib|zumab|tinib|ciclib|rafenib|ximab|umab|tug|parin))\b',  # INN stems
                    sentence
                )

                for match_tuple in compound_matches:
                    compound = match_tuple[0] or match_tuple[1]
                    if not compound or len(compound) < 3:
                        continue

                    # Skip common false positives
                    if compound.upper() in ('FDA', 'SEC', 'CEO', 'NDA', 'BLA', 'IND', 'EMA', 'USA', 'NYSE'):
                        continue

                    # Extract indication if present
                    indication = None
                    for ind_re in indication_patterns:
                        ind_match = re.search(ind_re, sentence)
                        if ind_match:
                            indication = ind_match.group(1).strip()[:100]
                            break

                    key = compound.lower()
                    confidence = base_confidence
                    if indication:
                        confidence = min(0.95, confidence + 0.10)

                    if key not in assets or assets[key].extract_confidence < confidence:
                        assets[key] = PipelineAsset(
                            compound_name=compound,
                            phase=phase_label,
                            indication=indication,
                            filing_accession=source_filing,
                            extract_confidence=confidence,
                        )

        result = list(assets.values())
        logger.info(f"Extracted {len(result)} pipeline assets from filing {source_filing}")
        return result
