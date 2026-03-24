"""MCP Adapter: orange_book
Feature: 015-assessment-dashboard-integration

Fetches patent and exclusivity data from the FDA Orange Book.
Uses the Drugs@FDA API to get submission/product data, then enriches
with patent/exclusivity from the Orange Book bulk CSV data endpoint.

Note: The Drugs@FDA JSON API does NOT include Orange Book patent data.
Patent/exclusivity info comes from the CSV files at:
  https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files

For biologics (BLA), the Orange Book has NO data — biologics have 12-year
BPCIA exclusivity tracked separately. This adapter returns the Drugs@FDA
submission data which includes sNDA/sBLA supplements with approval dates.
"""
from urllib.parse import quote

from .base import BaseAdapter


# Orange Book CSV endpoints (direct download, no auth required)
ORANGE_BOOK_PATENT_URL = "https://www.fda.gov/media/76860/download"  # patent.txt
ORANGE_BOOK_EXCLUSIVITY_URL = "https://www.fda.gov/media/76859/download"  # exclusivity.txt


class Adapter(BaseAdapter):
    """Adapter for FDA Drugs@FDA + Orange Book patent/exclusivity data."""

    @property
    def source_name(self) -> str:
        return "orange_book"

    @property
    def raw_table(self) -> str:
        return "orange_book"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """FDA Drugs@FDA API uses openFDA search syntax.

        This fetches product/submission data. Patent data must be enriched
        separately from the Orange Book CSV bulk download.
        """
        return f'{base_url}?search=openfda.generic_name:"{quote(drug_name)}"&limit=20'

    def normalize(self, api_response: dict) -> dict:
        """Normalize Drugs@FDA response and flatten products with submissions.

        Each product+submission becomes a separate record for bronze extraction.
        Adds application_number, product info, and submission dates.
        """
        results = api_response.get('results', [])
        if not results:
            return api_response

        # Flatten: one record per product with all its submissions
        records = []
        for app in results:
            app_number = app.get('application_number', '')
            sponsor = app.get('sponsor_name', '')
            for product in app.get('products', []):
                record = {
                    'application_number': app_number,
                    'sponsor_name': sponsor,
                    'brand_name': product.get('brand_name'),
                    'ingredient': (product.get('active_ingredients', [{}])[0] or {}).get('name'),
                    'strength': (product.get('active_ingredients', [{}])[0] or {}).get('strength'),
                    'dosage_form': product.get('dosage_form'),
                    'route': ', '.join(app.get('openfda', {}).get('route', [])),
                    'marketing_status': product.get('marketing_status'),
                    'te_code': product.get('te_code'),
                    'is_biologic': app_number.startswith('BLA'),
                    # Submissions carry approval dates
                    'submissions': [
                        {
                            'type': s.get('submission_type'),
                            'number': s.get('submission_number'),
                            'status': s.get('submission_status'),
                            'status_date': s.get('submission_status_date'),
                        }
                        for s in app.get('submissions', [])
                        if s.get('submission_status') == 'AP'
                    ],
                }
                records.append(record)

        return {**api_response, '_normalized_products': records}

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure we have at least one result."""
        results = normalized.get('results', [])
        return isinstance(results, list) and len(results) > 0
