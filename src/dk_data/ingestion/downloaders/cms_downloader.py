"""CMS Bulk File Downloader.

Downloads CMS Public Use Files using two resolution strategies:

1. DCAT catalog (data.cms.gov/data.json) — fetched once per day and cached.
   Each dataset entry has a catalog_uuid that maps to a distribution with a
   downloadURL.  CMS updates these URLs when new annual data is posted, so
   this approach never needs code changes to pick up new data.

2. Streaming JSON API (data.cms.gov/data-api/v1/dataset/{UUID}/data) —
   alternative to CSV download; returns paginated JSON records with column
   names exactly as CMS serves them.  Used by the fetcher layer when a
   file download is not required.

NPPES is the only source that bypasses catalog discovery — CMS publishes it
at a predictable URL pattern on download.cms.gov, not in data.json.

See GitHub issue data-kinetic/dk-data-FE#152.

Usage:
    from dk_data.ingestion.downloaders.cms_downloader import download_cms_file

    filepath, was_new = download_cms_file('cms_part_d_spending', year=2023)
    if filepath and was_new:
        load_cms_part_d_spending(filepath, source_year=2023)
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(os.getenv("CMS_DOWNLOAD_DIR", "/tmp/cms_downloads"))
_CATALOG_CACHE_PATH = DOWNLOAD_DIR / "_cms_catalog.json"
_CATALOG_MAX_AGE_DAYS = 1

REQUEST_TIMEOUT = 120
MAX_FILE_AGE_DAYS = 30


# ---------------------------------------------------------------------------
# Dataset registry
#
# Fields:
#   catalog_uuid   — UUID in data.cms.gov/data.json.  _discover_url_from_catalog()
#                    reads the live catalog (cached daily) to get the current CSV URL.
#   not_available  — True when CMS does not publish this as a standalone file.
#                    imaging and mental_health are specialty subsets of physician_puf.
#   note           — Explanation for non-standard entries.
#
# NPPES uses nppes_url_template instead — CMS publishes it at a known URL
# pattern on download.cms.gov, not via the data.json catalog.
# ---------------------------------------------------------------------------
CMS_DATASET_REGISTRY: dict[str, dict] = {
    # Drug spending
    "cms_part_d_spending": {
        "catalog_uuid": "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b",
        "description": "Medicare Part D Spending by Drug",
    },
    "cms_part_b_spending": {
        "catalog_uuid": "76a714ad-3a2c-43ac-b76d-9dadf8f7d890",
        "description": "Medicare Part B Spending by Drug",
    },
    "cms_medicaid_drug_spending": {
        "catalog_uuid": "be64fce3-e835-4589-b46b-024198e524a6",
        "description": "Medicaid Spending by Drug",
    },

    # Physician / practitioner
    "cms_physician_puf": {
        "catalog_uuid": "8889d81e-2ee7-448f-8713-f071038289b5",
        "description": "Medicare Physician & Other Practitioners – by Provider",
    },
    "cms_referring_providers": {
        "catalog_uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",
        "description": "Order and Referring Providers (combined file)",
    },
    "cms_ordering_providers": {
        # CMS publishes ordering and referring in one combined file.
        "catalog_uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",
        "description": "Order and Referring Providers (combined file)",
    },

    # Hospital / facility
    "cms_inpatient_puf": {
        "catalog_uuid": "690ddc6c-2767-4618-b277-420ffb2bf27c",
        "description": "Medicare Inpatient Hospitals – by Provider and Service",
    },
    "cms_outpatient_puf": {
        "catalog_uuid": "ccbc9a44-40d4-46b4-a709-5caa59212e50",
        "description": "Medicare Outpatient Hospitals – by Provider and Service",
    },
    "cms_hospital_general_info": {
        # provider-data portal — not in data.cms.gov/data.json
        "catalog_uuid": "xubh-q36u",
        "catalog_base": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "description": "Hospital General Information",
    },
    "cms_cost_reports_puf": {
        "catalog_uuid": "44060663-47d8-4ced-a115-b53b4c270acb",
        "description": "Hospital Provider Cost Report (HCRIS)",
    },

    # Post-acute care
    "cms_snf_puf": {
        "catalog_uuid": "eaed338b-847e-41b1-a4d3-a206f40dc72b",
        "description": "Medicare PAC Utilization – Skilled Nursing Facility",
    },
    "cms_hospice_puf": {
        "catalog_uuid": "4e73f1b5-82cb-4682-8ad2-28493f0b6840",
        "description": "Medicare PAC Utilization – Hospice",
    },
    "cms_home_health": {
        # provider-data portal — not in data.cms.gov/data.json
        "catalog_uuid": "6jpm-sxkc",
        "catalog_base": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "description": "Home Health Care Agencies",
    },

    # DME / lab / specialty services
    "cms_dme_puf": {
        "catalog_uuid": "a2d56d3f-3531-4315-9d87-e29986516b41",
        "description": "Medicare DME – by Supplier",
    },
    "cms_lab_services": {
        "catalog_uuid": "0e57f57d-0acc-4c9c-8f8c-973e3f4a3c4b",
        "description": "Medicare Clinical Laboratory Fee Schedule Private Payer Rates",
    },
    "cms_telehealth_puf": {
        "catalog_uuid": "939226be-b107-476e-8777-f199a840138a",
        "description": "Medicare Telehealth Trends",
    },

    # Opioid / specialty subsets
    "cms_opioid_puf": {
        # No standalone opioid-prescriber PUF in catalog; use Part D Prescribers by Provider.
        "catalog_uuid": "14d8e8a9-7e9b-4370-a044-bf97c46b4b44",
        "description": "Medicare Part D Prescribers – by Provider (NPI-level)",
        "note": "Standalone opioid PUF removed from data.cms.gov; using full Part D Prescribers file.",
    },
    "cms_imaging_puf": {
        "not_available": True,
        "description": "Medicare Imaging and Radiology Services PUF",
        "note": (
            "No standalone imaging PUF exists. "
            "Imaging is a specialty subset of cms_physician_puf (UUID 8889d81e). "
            "Filter on provider_type='Radiology' after loading physician_puf."
        ),
    },
    "cms_mental_health_puf": {
        "not_available": True,
        "description": "Medicare Mental Health Providers PUF",
        "note": (
            "No standalone mental health PUF exists. "
            "Mental health is a specialty subset of cms_physician_puf (UUID 8889d81e). "
            "Filter on provider_type like 'Psychiatry'/'Psychology' after loading physician_puf."
        ),
    },

    # Open payments
    "cms_open_payments": {
        "catalog_uuid": "e6b17c6a-2534-4207-a4a1-6746a14911ff",
        "description": "Open Payments General Payment Data",
    },

    # Geographic / population
    "cms_geographic_variation": {
        "catalog_uuid": "6219697b-8f6c-4164-bed4-cd9317c58ebc",
        "description": "Geographic Variation in Medicare Service Use",
    },
    "cms_enrollment_puf": {
        "catalog_uuid": "d7fabe1e-d19b-4333-9eff-e80e0643f2fd",
        "description": "Medicare Monthly Enrollment",
    },
    "cms_medicare_advantage": {
        "catalog_uuid": "8e989bc0-2260-49a7-9c6d-8e9e10af7cea",
        "description": "Medicare Advantage Geographic Variation PUF",
    },
    "cms_dual_eligible": {
        "catalog_uuid": "3ff3dcc3-7608-448d-9b35-4f184697e37c",
        "description": "CMS Program Statistics – Medicare-Medicaid Dual Enrollment",
    },
    "cms_chronic_conditions": {
        "catalog_uuid": "3f4e4f8e-4b1a-4b3a-8d8a-4b3a4f8e4b1a",
        "description": "Chronic Conditions Among Medicare Beneficiaries",
        "note": "Not in main data.cms.gov catalog; discovery may return None.",
    },

    # Claim-type / utilization summaries
    "cms_claim_type_puf": {
        "catalog_uuid": "164fc736-4179-4100-9f79-592b69e41975",
        "description": "Physician/Supplier Procedure Summary",
    },
    "cms_utilization_puf": {
        # Uses Physician by Provider as the closest available substitute.
        "catalog_uuid": "8889d81e-2ee7-448f-8713-f071038289b5",
        "description": "Medicare Physician PUF by Provider (utilization proxy)",
        "note": "No standalone utilization PUF in catalog; using Physician PUF as substitute.",
    },

    # NPPES — special: stable URL template on download.cms.gov, not in data.json
    "cms_nppes": {
        "nppes_url_template": (
            "https://download.cms.gov/nppes/"
            "NPPES_Data_Dissemination_{month}_{year}.zip"
        ),
        "description": "NPPES NPI Registry Monthly Dissemination",
    },
}

# data-api/v1 streaming endpoint — used by fetcher layer for JSON record access
CMS_DATA_API_BASE = "https://data.cms.gov/data-api/v1/dataset"


# ---------------------------------------------------------------------------
# Catalog discovery
# ---------------------------------------------------------------------------

def _get_catalog(force_refresh: bool = False) -> Optional[list]:
    """Fetch and cache the data.cms.gov DCAT catalog (data.json).

    Returns the list of dataset entries or None on failure.
    The catalog is cached to _CATALOG_CACHE_PATH for _CATALOG_MAX_AGE_DAYS.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not force_refresh and _CATALOG_CACHE_PATH.exists():
        age_days = (time.time() - _CATALOG_CACHE_PATH.stat().st_mtime) / 86400
        if age_days <= _CATALOG_MAX_AGE_DAYS:
            try:
                data = json.loads(_CATALOG_CACHE_PATH.read_text())
                return data.get("dataset", data) if isinstance(data, dict) else data
            except (json.JSONDecodeError, OSError):
                pass

    try:
        resp = requests.get(
            "https://data.cms.gov/data.json",
            timeout=REQUEST_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        catalog = resp.json()
        _CATALOG_CACHE_PATH.write_text(json.dumps(catalog))
        return catalog.get("dataset", [])
    except Exception as e:
        logger.warning(f"Failed to fetch CMS DCAT catalog: {e}")
        return None


def discover_year_uuids(parent_uuid: str, force_refresh: bool = False) -> dict[int, str]:
    """Discover year-specific dataset UUIDs from the CMS DCAT catalog.

    CMS publishes multi-year datasets with one distribution entry per service
    year.  Each distribution has:
      - title: e.g. "Medicare Physician ... - 2023"
      - accessURL: https://data.cms.gov/data-api/v1/dataset/<sub-uuid>/data

    This function fetches the catalog (cached 24h), finds the entry whose
    ``identifier`` contains ``parent_uuid``, then parses each distribution to
    extract year → sub-UUID pairs.

    Args:
        parent_uuid: The canonical dataset UUID (e.g. "8889d81e-...").
        force_refresh: If True, bypass the catalog cache.

    Returns:
        Dict mapping service_year (int) → sub-dataset UUID (str).
        Empty dict if the catalog is unavailable or the UUID is not found.
    """
    import re

    catalog = _get_catalog(force_refresh=force_refresh)
    if not catalog:
        logger.warning("CMS catalog unavailable — cannot discover year-specific UUIDs")
        return {}

    year_uuids: dict[int, str] = {}
    for dataset in catalog:
        identifier = dataset.get("identifier", "")
        if parent_uuid not in identifier:
            continue

        for dist in dataset.get("distribution", []):
            title = dist.get("title", "")
            # accessURL carries the sub-dataset UUID in the path
            access_url = dist.get("accessURL", "") or dist.get("downloadURL", "")

            # Extract year from distribution title (e.g. "... - 2023" or "2023 Data")
            year_matches = re.findall(r'\b(20\d{2})\b', title)
            if not year_matches:
                continue
            year = int(year_matches[-1])

            # Extract sub-UUID from access URL:
            # https://data.cms.gov/data-api/v1/dataset/<UUID>/data
            uuid_match = re.search(
                r'/dataset/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
                access_url,
            )
            if not uuid_match:
                continue
            uuid = uuid_match.group(1)

            if year not in year_uuids:
                year_uuids[year] = uuid

        break  # Found the matching dataset; no need to scan further

    if year_uuids:
        logger.info(
            "Discovered %d year-specific UUIDs for parent %s: %s",
            len(year_uuids), parent_uuid,
            {y: u[:8] + "..." for y, u in sorted(year_uuids.items())},
        )
    else:
        logger.warning(
            "No year-specific UUIDs found for parent UUID %s in CMS catalog",
            parent_uuid,
        )

    return year_uuids


def _discover_url_from_catalog(catalog_uuid: str, catalog_base: Optional[str] = None) -> Optional[str]:
    """Find the best CSV download URL for a dataset by UUID.

    Checks data.cms.gov/data.json first.  If catalog_base is set (provider-data
    portal), queries that endpoint instead.

    Returns the downloadURL string or None.
    """
    # Provider-data portal has a separate metastore API
    if catalog_base:
        try:
            resp = requests.get(
                f"{catalog_base}/{catalog_uuid}",
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            dataset = resp.json()
            for dist in dataset.get("distribution", []):
                dl_url = dist.get("downloadURL", "")
                if dl_url.lower().endswith(".csv"):
                    return dl_url
            # Return any downloadURL if no CSV found
            for dist in dataset.get("distribution", []):
                if dist.get("downloadURL"):
                    return dist["downloadURL"]
        except Exception as e:
            logger.warning(f"Provider-data catalog lookup failed for {catalog_uuid}: {e}")
        return None

    # Main data.cms.gov/data.json catalog
    datasets = _get_catalog()
    if not datasets:
        return None

    for dataset in datasets:
        identifier = dataset.get("identifier", "")
        if catalog_uuid not in identifier:
            continue
        # Prefer CSV; fall back to any downloadURL
        csv_url = None
        any_url = None
        for dist in dataset.get("distribution", []):
            media_type = dist.get("mediaType", "").lower()
            dl_url = dist.get("downloadURL", "")
            if not dl_url:
                continue
            if media_type == "text/csv" or dl_url.lower().endswith(".csv"):
                csv_url = dl_url
                break
            any_url = any_url or dl_url
        if csv_url:
            return csv_url
        if any_url:
            return any_url

    logger.warning(f"UUID {catalog_uuid} not found in CMS DCAT catalog")
    return None


def get_streaming_url(source_name: str) -> Optional[str]:
    """Return the data-api/v1 streaming endpoint URL for a source.

    This endpoint streams paginated JSON records directly — no CSV download.
    Column names match the CMS API (snake_case).

    Example:
        url = get_streaming_url('cms_part_d_spending')
        # https://data.cms.gov/data-api/v1/dataset/7e0b4365.../data
    """
    entry = CMS_DATASET_REGISTRY.get(source_name)
    if not entry or entry.get("not_available") or "nppes_url_template" in entry:
        return None
    uuid = entry.get("catalog_uuid")
    if not uuid:
        return None
    return f"{CMS_DATA_API_BASE}/{uuid}/data"


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _get_download_url(source_name: str, year: int) -> Optional[str]:
    """Resolve the current download URL for a CMS dataset.

    For NPPES: expands the URL template.
    For everything else: queries the live DCAT catalog (cached 24h).
    """
    entry = CMS_DATASET_REGISTRY.get(source_name)
    if not entry:
        logger.warning(f"No registry entry for source: {source_name}")
        return None

    if entry.get("not_available"):
        logger.warning(
            f"{source_name} is not available as a standalone download. "
            f"{entry.get('note', '')}"
        )
        return None

    # NPPES: templated URL, not in catalog
    if "nppes_url_template" in entry:
        month = "January"
        return entry["nppes_url_template"].format(month=month, year=year)

    # All other sources: live catalog lookup
    uuid = entry.get("catalog_uuid")
    if not uuid:
        logger.error(f"No catalog_uuid for {source_name} — cannot resolve URL")
        return None

    catalog_base = entry.get("catalog_base")
    url = _discover_url_from_catalog(uuid, catalog_base=catalog_base)
    if url:
        return url

    logger.error(
        f"Could not find download URL for {source_name} (UUID {uuid}) in CMS catalog. "
        "The dataset may have been removed or the UUID has changed."
    )
    return None


def _compute_file_hash(filepath: Path) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(source_name: str, year: int) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOAD_DIR / f"{source_name}_{year}.csv"


def _hash_file_path(source_name: str, year: int) -> Path:
    return DOWNLOAD_DIR / f"{source_name}_{year}.md5"


def download_cms_file(
    source_name: str,
    year: int = 2023,
    force: bool = False,
) -> tuple[Optional[str], bool]:
    """Download a CMS bulk file for the given source and year.

    Returns:
        (filepath, was_new): filepath is the local path to the downloaded file,
        was_new=True if the file was newly downloaded, False if using cache.
        Returns (None, False) if download failed or source is not available.
    """
    cache_path = _cache_path(source_name, year)
    hash_path = _hash_file_path(source_name, year)

    if not force and cache_path.exists():
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days <= MAX_FILE_AGE_DAYS:
            logger.info(
                f"Using cached {source_name} file (age: {age_days:.1f}d): {cache_path}"
            )
            return str(cache_path), False

    url = _get_download_url(source_name, year)
    if not url:
        logger.error(f"Cannot determine download URL for {source_name} year={year}")
        return None, False

    logger.info(f"Downloading {source_name} year={year} from {url}")

    try:
        resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        tmp_path = cache_path.with_suffix(".tmp")
        written = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    written += len(chunk)

        if written == 0:
            logger.error(f"Downloaded empty file for {source_name}")
            tmp_path.unlink(missing_ok=True)
            return None, False

        # Handle ZIP files: extract the largest CSV inside
        filename = urlparse(url).path.split("/")[-1].lower()
        content_type = resp.headers.get("content-type", "")
        if filename.endswith(".zip") or content_type.startswith("application/zip"):
            import zipfile

            with zipfile.ZipFile(tmp_path) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    logger.error(f"No CSV found in ZIP for {source_name}")
                    tmp_path.unlink(missing_ok=True)
                    return None, False
                csv_names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
                zf.extract(csv_names[0], DOWNLOAD_DIR)
                extracted = DOWNLOAD_DIR / csv_names[0]
                extracted.rename(cache_path)
            tmp_path.unlink(missing_ok=True)
        else:
            tmp_path.rename(cache_path)

        file_hash = _compute_file_hash(cache_path)
        hash_path.write_text(file_hash)

        logger.info(
            f"Downloaded {source_name} year={year}: "
            f"{cache_path.stat().st_size / 1024 / 1024:.1f} MB, hash={file_hash[:8]}"
        )
        return str(cache_path), True

    except requests.RequestException as e:
        logger.error(f"Download failed for {source_name}: {e}")
        return None, False
    except Exception as e:
        logger.error(f"Unexpected error downloading {source_name}: {e}")
        return None, False


def download_all_cms_sources(year: int = 2023, force: bool = False) -> dict[str, str]:
    """Download all registered CMS sources for a given year.

    Returns a dict mapping source_name -> local filepath for successful downloads.
    """
    results = {}
    for source_name, entry in CMS_DATASET_REGISTRY.items():
        if entry.get("not_available"):
            logger.info(f"Skipping {source_name}: not available as standalone download")
            continue
        filepath, _ = download_cms_file(source_name, year=year, force=force)
        if filepath:
            results[source_name] = filepath
        else:
            logger.warning(f"Failed to download {source_name}")
    return results
