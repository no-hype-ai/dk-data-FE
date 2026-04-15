"""Conference Abstracts fetcher — scrapes abstracts from major medical conferences.

Target conferences (by society acronym):
  - AAD   (American Academy of Dermatology)
  - EADV  (European Academy of Dermatology and Venereology)
  - ACR   (American College of Rheumatology)
  - EULAR (European Alliance of Associations for Rheumatology)
  - ATS   (American Thoracic Society)
  - AAAAI (American Academy of Allergy, Asthma & Immunology)
  - ASCO  (American Society of Clinical Oncology)
  - ESMO  (European Society for Medical Oncology)
  - ASH   (American Society of Hematology)
  - AHA   (American Heart Association)
  - ESC   (European Society of Cardiology)
  - ADA   (American Diabetes Association)
  - EASD  (European Association for the Study of Diabetes)
  - DDW   (Digestive Disease Week)
  - UEGW  (United European Gastroenterology Week)

Target table: mol_raw.conference_abstracts
Feature: 006-claims-engine-data-gaps (T078)
"""

import logging
from typing import Any, Dict, List

from .base import BaseFetcher

logger = logging.getLogger(__name__)

# Conference registry: (acronym, full_name, typical abstract portal URL)
TARGET_CONFERENCES: List[Dict[str, str]] = [
    {"acronym": "AAD",   "name": "American Academy of Dermatology",                  "url": "https://aad.confex.com"},
    {"acronym": "EADV",  "name": "European Academy of Dermatology and Venereology",  "url": "https://eadv.org/scientific-programme"},
    {"acronym": "ACR",   "name": "American College of Rheumatology",                 "url": "https://acrabstracts.org"},
    {"acronym": "EULAR", "name": "European Alliance of Associations for Rheumatology", "url": "https://scientific.sparx-ip.net/archiveeular"},
    {"acronym": "ATS",   "name": "American Thoracic Society",                        "url": "https://www.abstractsonline.com/pp8/#!/ats"},
    {"acronym": "AAAAI", "name": "American Academy of Allergy, Asthma & Immunology", "url": "https://annualmeeting.aaaai.org"},
    {"acronym": "ASCO",  "name": "American Society of Clinical Oncology",            "url": "https://meetings.asco.org/abstracts-presentations"},
    {"acronym": "ESMO",  "name": "European Society for Medical Oncology",            "url": "https://www.esmo.org/meeting-calendar"},
    {"acronym": "ASH",   "name": "American Society of Hematology",                   "url": "https://ash.confex.com"},
    {"acronym": "AHA",   "name": "American Heart Association",                       "url": "https://www.abstractsonline.com/pp8/#!/aha"},
    {"acronym": "ESC",   "name": "European Society of Cardiology",                   "url": "https://esc365.escardio.org"},
    {"acronym": "ADA",   "name": "American Diabetes Association",                    "url": "https://diabetesjournals.org/diabetes/issue/browse-by-year"},
    {"acronym": "EASD",  "name": "European Association for the Study of Diabetes",   "url": "https://www.easd.org/annual-meeting"},
    {"acronym": "DDW",   "name": "Digestive Disease Week",                           "url": "https://ddw.org/abstracts"},
    {"acronym": "UEGW",  "name": "United European Gastroenterology Week",            "url": "https://ueg.eu/week"},
]

FETCHER_CONFIG = {
    "source_name": "conference_abstracts",
    "target_table": "mol_raw.conference_abstracts",
    "schedule": "monthly",
    "notes": (
        "Each conference has a different abstract portal with different "
        "scraping requirements. Most use Confex, ScholarOne, or custom "
        "platforms. Implementation should handle embargo dates — abstracts "
        "under embargo must set embargo_date and publication_date accordingly."
    ),
}


class ConferenceAbstractsFetcher(BaseFetcher):
    """Fetcher for medical conference abstracts across 15 target societies."""

    SOURCE_NAME = "conference_abstracts"
    BASE_URL = ""  # varies per conference

    def get_latest_url(self) -> str:
        # No single URL — each conference has its own portal
        return "https://clinicaltrials.gov"  # placeholder

    def fetch(self, **kwargs) -> Dict[str, Any]:
        """Fetch conference abstracts from target medical conferences.

        TODO: Implement per-conference scraper dispatchers. Each conference
        requires its own scraping logic due to different abstract portal
        platforms (Confex, ScholarOne, custom). Must respect embargo dates
        by setting embargo_date/publication_date fields. Upsert into
        mol_raw.conference_abstracts.

        Args:
            conference: Optional conference acronym to fetch (e.g. 'ASCO').
                        If not provided, fetches from all target conferences.

        Returns:
            Fetch result dictionary with status, records, count, hash.
        """
        raise NotImplementedError(
            "ConferenceAbstractsFetcher.fetch() is a stub — "
            "implementation pending per-conference scraper development."
        )
