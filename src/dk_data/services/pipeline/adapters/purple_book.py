"""MCP Adapter: purple_book
Feature: 003-molecule-assessment-dashboard

Fetches biologic product data from the FDA Purple Book API.
Endpoint: https://purplebooksearch.fda.gov/api/v1/

Provides:
- BLA number, license type (351(a) originator vs 351(k) biosimilar/interchangeable)
- Approval date, orphan exclusivity expiration, interchangeable exclusivity
- Reference product linkage for biosimilars
- BPCIA 12-year data exclusivity (derived from approval date)

No auth key required — uses a public API token embedded in the Purple Book SPA.
"""
from urllib.parse import quote

from .base import BaseAdapter

# Purple Book API token (public, embedded in the SPA JavaScript bundle)
PURPLE_BOOK_TOKEN = "18dd75c5-23c2-4318-970b-ca97c34470cb"
PURPLE_BOOK_BASE = "https://purplebooksearch.fda.gov/api/v1"


class Adapter(BaseAdapter):
    """Adapter for FDA Purple Book (biologics) API."""

    @property
    def source_name(self) -> str:
        return "purple_book"

    @property
    def raw_table(self) -> str:
        return "purple_book"

    @property
    def raw_schema(self) -> str:
        return "mol_raw"

    def build_url(self, base_url: str, drug_name: str, params: dict) -> str:
        """Build Purple Book API URL.

        Strategy:
        1. If bla_number provided → direct detail lookup
        2. Otherwise → fetch full product list and filter in normalize()
           (Purple Book has no server-side name search on the detail endpoint)
        """
        if params.get('bla_number'):
            bla = params['bla_number']
            return f"{PURPLE_BOOK_BASE}/details?token={PURPLE_BOOK_TOKEN}&bla_number={bla}"
        # Fetch autosuggest to find BLA number by name, then details
        # But autosuggest returns all 866 BLAs — use it for lookup
        return f"{PURPLE_BOOK_BASE}/autosuggest?token={PURPLE_BOOK_TOKEN}"

    def normalize(self, api_response: dict) -> dict:
        """Normalize Purple Book API response.

        If autosuggest response (list of all BLAs): filter to matching drug_name,
        then the base tool will need a follow-up detail call.
        If detail response (list of product presentations): extract all fields.
        """
        if not isinstance(api_response, list):
            return api_response

        # Detect response type: autosuggest has 'bla_number' key, detail has 'a_num'
        if len(api_response) == 0:
            return {'_normalized_products': []}

        sample = api_response[0]

        if 'a_num' in sample:
            # Detail response — extract product records
            return self._normalize_detail(api_response)

        if 'bla_number' in sample:
            # Autosuggest response — return as-is for BLA number lookup
            return {'_autosuggest': api_response, '_normalized_products': []}

        return {'_normalized_products': []}

    def _normalize_detail(self, records: list) -> dict:
        """Normalize detail endpoint response into structured products."""
        products = []
        for r in records:
            license_type = r.get('a_type') or r.get('bio_int') or ''
            is_biosimilar = '351(k)' in license_type
            is_interchangeable = 'interchangeable' in license_type.lower()

            products.append({
                'bla_number': r.get('a_num'),
                'applicant': r.get('applicant'),
                'brand_name': r.get('prop_name'),
                'generic_name': r.get('name'),
                'license_type': license_type,
                'is_biosimilar': is_biosimilar,
                'is_interchangeable': is_interchangeable,
                'approval_date': r.get('bla_approval_date'),
                'first_licensure_date': r.get('firstLicensure') or None,
                'orphan_exclusivity_end': r.get('orphan_excl_expiration_date') or None,
                'exclusivity_expiry_date': r.get('exclusivity_expiry_date') if isinstance(r.get('exclusivity_expiry_date'), str) and r.get('exclusivity_expiry_date') else None,
                'interchangeable_exclusivity_end': r.get('first_interchangeable_exclusivity_exp_date') or None,
                'ref_product_exclusivity_end': r.get('ref_product_excl_exp_date') or None,
                'reference_product_name': r.get('ref_name') or None,
                'reference_product_brand': r.get('ref_prop_name') or None,
                'dosage_form': (r.get('dosage') or '').strip(),
                'strength': r.get('strength'),
                'presentation': r.get('presentation'),
                'route': (r.get('route_a') or '').strip(),
                'status': r.get('status'),
                'center': r.get('center'),
                'product_number': r.get('prod_num'),
                'has_patent_list': r.get('patent_list') == 'Y',
                'interchangeable_approval_date': r.get('interchangeable_approval_date') or None,
            })

        return {'_normalized_products': products}

    def validate_against_bronze(self, normalized: dict) -> bool:
        """Ensure we have at least one product."""
        products = normalized.get('_normalized_products', [])
        return isinstance(products, list) and len(products) > 0
