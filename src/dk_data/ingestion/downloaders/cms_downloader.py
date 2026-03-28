"""CMS Bulk File Downloader.

Fetches annual CMS Public Use Files (PUFs) from data.cms.gov using the
CKAN-based data portal API. Downloads to /tmp/cms_downloads/ and tracks
last-downloaded file hash to avoid re-fetching unchanged files.

Usage:
    from dk_data.ingestion.downloaders.cms_downloader import download_cms_file

    filepath, was_new = download_cms_file('cms_part_d_spending', year=2023)
    if filepath and was_new:
        load_cms_part_d_spending(filepath, source_year=2023)
"""

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Download destination — use /tmp which is always writable even in readonly containers
DOWNLOAD_DIR = Path(os.getenv("CMS_DOWNLOAD_DIR", "/tmp/cms_downloads"))

# CMS data.cms.gov dataset registry
# Each entry maps a source name to one or more dataset resource identifiers.
# The 'package_id' is the dataset slug on data.cms.gov (CKAN API).
# 'resource_format' filters to the correct resource (CSV preferred).
# 'url_override' bypasses CKAN discovery for sources with stable direct URLs.
CMS_DATASET_REGISTRY: dict[str, dict] = {
    "cms_part_d_spending": {
        "package_id": "medicare-part-d-spending-by-drug",
        "resource_format": "CSV",
        "description": "Medicare Part D Drug Spending by Drug",
    },
    "cms_part_b_spending": {
        "package_id": "medicare-part-b-spending-by-drug",
        "resource_format": "CSV",
        "description": "Medicare Part B Drug Spending by Drug",
    },
    "cms_physician_puf": {
        "package_id": "medicare-physician-other-practitioners-by-provider",
        "resource_format": "CSV",
        "description": "Medicare Physician & Other Practitioners – by Provider",
    },
    "cms_inpatient_puf": {
        "package_id": "medicare-inpatient-hospitals-by-provider-and-service",
        "resource_format": "CSV",
        "description": "Medicare Inpatient Hospitals – by Provider and Service",
    },
    "cms_outpatient_puf": {
        "package_id": "medicare-outpatient-hospitals-by-provider-and-service",
        "resource_format": "CSV",
        "description": "Medicare Outpatient Hospitals – by Provider and Service",
    },
    "cms_hospital_general_info": {
        "package_id": "hospital-general-information",
        "resource_format": "CSV",
        "description": "Hospital General Information",
    },
    "cms_open_payments": {
        "package_id": "open-payments-general-payment-data",
        "resource_format": "CSV",
        "description": "Open Payments – General Payment Data",
    },
    "cms_nppes": {
        "url_override": "https://download.cms.gov/nppes/NPPES_Data_Dissemination_{month}_{year}.zip",
        "description": "NPPES NPI Registry Monthly Dissemination",
        "format": "zip_csv",
    },
    "cms_home_health": {
        "package_id": "home-health-care-agencies",
        "resource_format": "CSV",
        "description": "Home Health Care Agencies",
    },
    "cms_snf_puf": {
        "package_id": "medicare-skilled-nursing-facility-puf",
        "resource_format": "CSV",
        "description": "Medicare Skilled Nursing Facility PUF",
    },
    "cms_referring_providers": {
        "package_id": "medicare-referring-providers",
        "resource_format": "CSV",
        "description": "Medicare Referring Providers",
    },
    "cms_ordering_providers": {
        "package_id": "medicare-ordering-and-referring",
        "resource_format": "CSV",
        "description": "Medicare Ordering and Referring Providers",
    },
    "cms_dme_puf": {
        "package_id": "medicare-durable-medical-equipment-devices-supplies-by-referring-provider-and-service",
        "resource_format": "CSV",
        "description": "Medicare DME PUF",
    },
    "cms_hospice_puf": {
        "package_id": "medicare-hospice-providers",
        "resource_format": "CSV",
        "description": "Medicare Hospice Providers PUF",
    },
    "cms_lab_services": {
        "package_id": "medicare-clinical-laboratory-fee-schedule",
        "resource_format": "CSV",
        "description": "Medicare Clinical Laboratory Fee Schedule",
    },
    "cms_imaging_puf": {
        "package_id": "medicare-imaging-and-radiology-services",
        "resource_format": "CSV",
        "description": "Medicare Imaging and Radiology Services PUF",
    },
    "cms_mental_health_puf": {
        "package_id": "medicare-mental-health-providers",
        "resource_format": "CSV",
        "description": "Medicare Mental Health Providers PUF",
    },
    "cms_telehealth_puf": {
        "package_id": "medicare-telehealth-utilization",
        "resource_format": "CSV",
        "description": "Medicare Telehealth Utilization PUF",
    },
    "cms_opioid_puf": {
        "package_id": "medicare-part-d-opioid-prescriber-summary-file",
        "resource_format": "CSV",
        "description": "Medicare Part D Opioid Prescribing by Provider (prescriber-level)",
    },
    "cms_geographic_variation": {
        "package_id": "geographic-variation-in-service-use",
        "resource_format": "CSV",
        "description": "Geographic Variation in Medicare Service Use",
    },
    "cms_chronic_conditions": {
        "package_id": "chronic-conditions-among-medicare-beneficiaries",
        "resource_format": "CSV",
        "description": "Chronic Conditions Among Medicare Beneficiaries",
    },
    "cms_dual_eligible": {
        "package_id": "medicare-medicaid-dual-eligible-beneficiaries",
        "resource_format": "CSV",
        "description": "Medicare-Medicaid Dual Eligible Beneficiaries",
    },
    "cms_enrollment_puf": {
        "package_id": "medicare-monthly-enrollment",
        "resource_format": "CSV",
        "description": "Medicare Monthly Enrollment",
    },
    "cms_medicare_advantage": {
        "package_id": "medicare-advantage-contract-and-enrollment-data",
        "resource_format": "CSV",
        "description": "Medicare Advantage Contract and Enrollment Data",
    },
    "cms_medicaid_drug_spending": {
        "package_id": "medicaid-spending-by-drug",
        "resource_format": "CSV",
        "description": "Medicaid Spending by Drug",
    },
    "cms_cost_reports_puf": {
        "package_id": "cost-reports",
        "resource_format": "CSV",
        "description": "Hospital Cost Reports (HCRIS)",
    },
    "cms_claim_type_puf": {
        "package_id": "medicare-fee-for-service-claims-summary",
        "resource_format": "CSV",
        "description": "Medicare Fee-for-Service Claims by Type",
    },
    "cms_utilization_puf": {
        "package_id": "medicare-utilization-and-payment-data",
        "resource_format": "CSV",
        "description": "Medicare Utilization and Payment Data",
    },
}

CKAN_BASE = "https://data.cms.gov/api/3/action"
REQUEST_TIMEOUT = 60
MAX_FILE_AGE_DAYS = 30  # Re-download if cached file is older than this


def _get_download_url(source_name: str, year: int) -> Optional[str]:
    """Discover the download URL for a CMS dataset via CKAN API."""
    entry = CMS_DATASET_REGISTRY.get(source_name)
    if not entry:
        logger.warning(f"No registry entry for source: {source_name}")
        return None

    # Direct URL override (e.g., NPPES which has a known stable URL pattern)
    if "url_override" in entry:
        month = "January"  # CMS NPPES monthly releases; use Jan for annual
        url = entry["url_override"].format(month=month, year=year)
        return url

    package_id = entry.get("package_id")
    if not package_id:
        logger.warning(f"No package_id for source: {source_name}")
        return None

    # Query CKAN API
    # NOTE: data.cms.gov previously served a CKAN API at /api/3/action/. As of
    # 2025-2026 the portal was migrated to a React SPA; the /api/3/ endpoints now
    # return HTML instead of JSON.  We detect this and log a clear error so
    # operators know the root cause rather than seeing a cryptic JSONDecodeError.
    try:
        resp = requests.get(
            f"{CKAN_BASE}/package_show",
            params={"id": package_id},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "html" in content_type or resp.text.lstrip().startswith("<!"):
            logger.error(
                f"CMS CKAN API returned HTML instead of JSON for {package_id}. "
                "The data.cms.gov CKAN API appears to be deprecated. "
                "Add a 'url_override' entry in CMS_DATASET_REGISTRY to bypass. "
                "See GitHub issue data-kinetic/dk-data-FE#152 for tracking."
            )
            return None

        data = resp.json()

        if not data.get("success"):
            logger.warning(f"CKAN API returned failure for {package_id}: {data.get('error')}")
            return None

        resources = data["result"].get("resources", [])
        if not resources:
            logger.warning(f"No resources found for {package_id}")
            return None

        # Filter by format and find most recent for target year
        target_format = entry.get("resource_format", "CSV")
        candidates = [
            r for r in resources
            if r.get("format", "").upper() == target_format.upper()
            and str(year) in (r.get("name", "") + r.get("url", "") + r.get("description", ""))
        ]

        if not candidates:
            # Fall back to most recent CSV regardless of year
            candidates = [
                r for r in resources
                if r.get("format", "").upper() == target_format.upper()
            ]

        if not candidates:
            logger.warning(f"No {target_format} resources found for {package_id}")
            return None

        # Sort by created date descending
        candidates.sort(
            key=lambda r: r.get("created", ""),
            reverse=True,
        )
        return candidates[0]["url"]

    except (requests.RequestException, ValueError) as e:
        logger.error(f"Failed to query CKAN API for {source_name}: {e}")
        return None


def _compute_file_hash(filepath: Path) -> str:
    """Compute MD5 hash of file contents."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(source_name: str, year: int) -> Path:
    """Return the local cache path for a downloaded file."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOAD_DIR / f"{source_name}_{year}.csv"


def _hash_file_path(source_name: str, year: int) -> Path:
    """Return the path to the hash tracking file."""
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
        Returns (None, False) if download failed.
    """
    cache_path = _cache_path(source_name, year)
    hash_path = _hash_file_path(source_name, year)

    # Check cache: use if fresh and not forced
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

        # Stream to temp file, then move to cache path
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

        # Handle zip files: extract the CSV
        filename = urlparse(url).path.split("/")[-1].lower()
        if filename.endswith(".zip") or resp.headers.get("content-type", "").startswith(
            "application/zip"
        ):
            import zipfile

            with zipfile.ZipFile(tmp_path) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    logger.error(f"No CSV found in ZIP for {source_name}")
                    tmp_path.unlink(missing_ok=True)
                    return None, False
                # Use the largest CSV (likely the main data file)
                csv_names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
                zf.extract(csv_names[0], DOWNLOAD_DIR)
                extracted = DOWNLOAD_DIR / csv_names[0]
                extracted.rename(cache_path)
            tmp_path.unlink(missing_ok=True)
        else:
            tmp_path.rename(cache_path)

        # Store hash for future change detection
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

    Returns:
        Dict mapping source_name -> local filepath (only successfully downloaded sources).
    """
    results = {}
    for source_name in CMS_DATASET_REGISTRY:
        filepath, _ = download_cms_file(source_name, year=year, force=force)
        if filepath:
            results[source_name] = filepath
        else:
            logger.warning(f"Failed to download {source_name}")
    return results
