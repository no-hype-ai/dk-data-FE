"""CMS Bulk File Downloader.

Fetches annual CMS Public Use Files (PUFs) from data.cms.gov.

The CKAN API (data.cms.gov/api/3/action/) was deprecated in 2025-2026 when CMS
migrated to a React SPA. All sources now use direct `url_override` entries or
dynamic discovery via the DCAT catalog at data.cms.gov/data.json.

See GitHub issue data-kinetic/dk-data-FE#152 for history.

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

# Download destination — use /tmp which is always writable even in readonly containers
DOWNLOAD_DIR = Path(os.getenv("CMS_DOWNLOAD_DIR", "/tmp/cms_downloads"))

# Path to cache the data.cms.gov DCAT catalog
_CATALOG_CACHE_PATH = DOWNLOAD_DIR / "_cms_catalog.json"
_CATALOG_MAX_AGE_DAYS = 1  # Re-fetch catalog if older than 1 day

# CMS dataset registry.
#
# Fields:
#   url_override  – Direct CSV (or ZIP) download URL. Takes precedence over everything.
#   catalog_uuid  – Dataset UUID in data.cms.gov/data.json for dynamic discovery.
#   description   – Human-readable label.
#   not_available – True if no downloadable file exists; download will return None.
#   note          – Explanation for non-standard entries.
#
# CKAN `package_id` approach is fully removed — it returned HTML since ~2025.
CMS_DATASET_REGISTRY: dict[str, dict] = {
    # ------------------------------------------------------------------ #
    # Drug spending                                                        #
    # ------------------------------------------------------------------ #
    "cms_part_d_spending": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-05/"
            "56d95a8b-138c-4b60-84a5-613fbab7197f/DSD_PTD_RY25_P04_V10_DY23_BGM.csv"
        ),
        "catalog_uuid": "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b",
        "description": "Medicare Part D Spending by Drug (DY2023)",
    },
    "cms_part_b_spending": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-05/"
            "f52d5fcd-8d93-481d-9173-6219813e4efb/"
            "DSD_PTB_RY25_P06_V10_DYT23_HCPCS-%20250430.csv"
        ),
        "catalog_uuid": "76a714ad-3a2c-43ac-b76d-9dadf8f7d890",
        "description": "Medicare Part B Spending by Drug (DY2023)",
    },
    "cms_medicaid_drug_spending": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-05/"
            "113322af-a725-4df3-95a6-dfeb03756160/DSD_MCD_RY25_P06_V20_D23_BGM.csv"
        ),
        "catalog_uuid": "be64fce3-e835-4589-b46b-024198e524a6",
        "description": "Medicaid Spending by Drug (DY2023)",
    },
    # ------------------------------------------------------------------ #
    # Physician / practitioner                                            #
    # ------------------------------------------------------------------ #
    "cms_physician_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-04/"
            "22edfd1e-d17a-4478-ad6b-92cac2a5a3c4/MUP_PHY_R25_P05_V20_D23_Prov.csv"
        ),
        "catalog_uuid": "8889d81e-2ee7-448f-8713-f071038289b5",
        "description": "Medicare Physician & Other Practitioners – by Provider (DY2023)",
    },
    "cms_referring_providers": {
        # CMS publishes ordering AND referring in one combined file.
        "url_override": (
            "https://data.cms.gov/sites/default/files/2026-03/"
            "4a5b5b2b-2aa0-4b70-809b-533f5be552d8/OrderReferring_20260327.csv"
        ),
        "catalog_uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",
        "description": "Order and Referring Providers (combined file)",
    },
    "cms_ordering_providers": {
        # Same combined file as cms_referring_providers.
        "url_override": (
            "https://data.cms.gov/sites/default/files/2026-03/"
            "4a5b5b2b-2aa0-4b70-809b-533f5be552d8/OrderReferring_20260327.csv"
        ),
        "catalog_uuid": "c99b5865-1119-4436-bb80-c5af2773ea1f",
        "description": "Order and Referring Providers (combined file)",
    },
    # ------------------------------------------------------------------ #
    # Hospital / facility                                                  #
    # ------------------------------------------------------------------ #
    "cms_inpatient_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-05/"
            "ca1c9013-8c7c-4560-a4a1-28cf7e43ccc8/MUP_INP_RY25_P03_V10_DY23_PrvSvc.CSV"
        ),
        "catalog_uuid": "690ddc6c-2767-4618-b277-420ffb2bf27c",
        "description": "Medicare Inpatient Hospitals – by Provider and Service (DY2023)",
    },
    "cms_outpatient_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-08/"
            "bceaa5e1-e58c-4109-9f05-832fc5e6bbc8/MUP_OUT_RY25_P04_V10_DY23_Prov_Svc.csv"
        ),
        "catalog_uuid": "ccbc9a44-40d4-46b4-a709-5caa59212e50",
        "description": "Medicare Outpatient Hospitals – by Provider and Service (DY2023)",
    },
    "cms_hospital_general_info": {
        # Served from provider-data portal, not data.cms.gov/data.json
        "url_override": (
            "https://data.cms.gov/provider-data/sites/default/files/resources/"
            "893c372430d9d71a1c52737d01239d47_1770163599/Hospital_General_Information.csv"
        ),
        "catalog_uuid": "xubh-q36u",
        "description": "Hospital General Information (provider-data portal)",
    },
    "cms_cost_reports_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2026-01/"
            "3c39f483-c7e0-4025-8396-4df76942e10f/CostReport_2023_Final.csv"
        ),
        "catalog_uuid": "44060663-47d8-4ced-a115-b53b4c270acb",
        "description": "Hospital Provider Cost Report (HCRIS 2023)",
    },
    # ------------------------------------------------------------------ #
    # Post-acute care                                                      #
    # ------------------------------------------------------------------ #
    "cms_snf_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-08/"
            "b646c0b9-5fe0-475c-8820-007680020fdc/"
            "RY_2025_RY_25_PAC_PUF_SNF_2023_main_final_unformatted.csv"
        ),
        "catalog_uuid": "eaed338b-847e-41b1-a4d3-a206f40dc72b",
        "description": "Medicare PAC Utilization – Skilled Nursing Facility (RY2025/DY2023)",
    },
    "cms_hospice_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-08/"
            "7c92ef92-85ff-4f2a-a1a6-b1f4f25210e4/"
            "RY_2025_RY_25_PAC_PUF_HOS_2023_main_final_unformatted.csv"
        ),
        "catalog_uuid": "4e73f1b5-82cb-4682-8ad2-28493f0b6840",
        "description": "Medicare PAC Utilization – Hospice (RY2025/DY2023)",
    },
    "cms_home_health": {
        # Served from provider-data portal
        "url_override": (
            "https://data.cms.gov/provider-data/sites/default/files/resources/"
            "d6258a04bfe1a4492ad2e80ca05572aa_1767204345/HH_Provider_Jan2026.csv"
        ),
        "catalog_uuid": "6jpm-sxkc",
        "description": "Home Health Care Agencies (provider-data portal, Jan 2026)",
    },
    # ------------------------------------------------------------------ #
    # DME / lab / specialty services                                       #
    # ------------------------------------------------------------------ #
    "cms_dme_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-06/"
            "5b10992b-8290-4b93-b036-0c233020d7da/mup_dme_ry25_p05_v10_dy23_supr.csv"
        ),
        "catalog_uuid": "a2d56d3f-3531-4315-9d87-e29986516b41",
        "description": "Medicare DME – by Supplier (DY2023)",
    },
    "cms_lab_services": {
        # Latest available CSV is 2018; newer data requires API access
        "url_override": (
            "https://data.cms.gov/sites/default/files/2021-12/"
            "CLFS%20Applicable%20Information%202018%20Raw%20Data%20File-updated%2012152021.csv"
        ),
        "catalog_uuid": "0e57f57d-0acc-4c9c-8f8c-973e3f4a3c4b",
        "description": "Medicare Clinical Laboratory Fee Schedule Private Payer Rates (2018)",
        "note": "Only 2018 CSV available; newer years require API streaming.",
    },
    "cms_telehealth_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2026-03/"
            "TMEDTREND_PUBLIC_260311.csv"
        ),
        "catalog_uuid": "939226be-b107-476e-8777-f199a840138a",
        "description": "Medicare Telehealth Trends (aggregate quarterly, through Q4 2025)",
    },
    # ------------------------------------------------------------------ #
    # Opioid / mental health / imaging (specialty subsets)                #
    # ------------------------------------------------------------------ #
    "cms_opioid_puf": {
        # No separate opioid-prescriber PUF in data.json; use Part D Prescribers by Provider.
        # This has NPI-level opioid prescribing columns alongside all other Part D drugs.
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-04/"
            "750769a3-bb0f-4f05-81dc-7dcb6e105cb0/MUP_DPR_RY25_P04_V10_DY23_NPI.csv"
        ),
        "catalog_uuid": "14d8e8a9-7e9b-4370-a044-bf97c46b4b44",
        "description": "Medicare Part D Prescribers – by Provider (NPI-level, DY2023)",
        "note": "Standalone opioid PUF removed from data.cms.gov; using full Part D Prescribers file.",
    },
    "cms_imaging_puf": {
        # No standalone imaging PUF. Imaging is a specialty subset of Physician PUF.
        "not_available": True,
        "description": "Medicare Imaging and Radiology Services PUF",
        "note": (
            "CMS does not publish a standalone imaging PUF. "
            "Imaging data is a specialty subset of cms_physician_puf (UUID 8889d81e). "
            "Filter on specialty_desc='Radiology' or similar after loading physician_puf."
        ),
    },
    "cms_mental_health_puf": {
        # No standalone mental health PUF. Mental health is a specialty subset of Physician PUF.
        "not_available": True,
        "description": "Medicare Mental Health Providers PUF",
        "note": (
            "CMS does not publish a standalone mental health PUF. "
            "Mental health data is a specialty subset of cms_physician_puf (UUID 8889d81e). "
            "Filter on specialty_desc like 'Psychiatry' or 'Psychology' after loading physician_puf."
        ),
    },
    # ------------------------------------------------------------------ #
    # Open payments                                                        #
    # ------------------------------------------------------------------ #
    "cms_open_payments": {
        # Served from openpaymentsdata.cms.gov (not data.cms.gov)
        "url_override": (
            "https://download.cms.gov/openpayments/PGYR2024_P01232026_01102026/"
            "OP_DTL_GNRL_PGYR2024_P01232026_01102026.csv"
        ),
        "catalog_uuid": "e6b17c6a-2534-4207-a4a1-6746a14911ff",
        "description": "Open Payments General Payment Data (PY2024)",
    },
    # ------------------------------------------------------------------ #
    # Geographic / population                                             #
    # ------------------------------------------------------------------ #
    "cms_geographic_variation": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-03/"
            "a40ac71d-9f80-4d99-92d2-fd149433d7d8/"
            "2014-2023%20Medicare%20Fee-for-Service%20Geographic%20Variation%20Public%20Use%20File.csv"
        ),
        "catalog_uuid": "6219697b-8f6c-4164-bed4-cd9317c58ebc",
        "description": "Geographic Variation in Medicare Service Use (2014-2023 combined)",
    },
    "cms_enrollment_puf": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2026-03/"
            "c2e42f20-57f6-4bbf-95a7-5267cec3f77c/"
            "Medicare%20Monthly%20Enrollment%20Data_December%202025.csv"
        ),
        "catalog_uuid": "d7fabe1e-d19b-4333-9eff-e80e0643f2fd",
        "description": "Medicare Monthly Enrollment (through December 2025)",
    },
    "cms_medicare_advantage": {
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-06/"
            "a0f6cfe0-b67c-44ef-807d-a901921ed1ee/MA%20GV%20PUF%202016-2022_RY_2025.csv"
        ),
        "catalog_uuid": "8e989bc0-2260-49a7-9c6d-8e9e10af7cea",
        "description": "Medicare Advantage Geographic Variation PUF 2016-2022 (RY2025)",
    },
    "cms_dual_eligible": {
        # Only available as ZIP; the existing zip_csv extraction logic handles this.
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-09/"
            "1104c73c-6cb7-422c-bb24-73236d1b5767/"
            "MDCR%20ENROLL%20AB%2040-48_CPS_02E_2023.zip"
        ),
        "catalog_uuid": "3ff3dcc3-7608-448d-9b35-4f184697e37c",
        "description": "CMS Program Statistics – Medicare-Medicaid Dual Enrollment (2023, ZIP)",
    },
    "cms_chronic_conditions": {
        # Not in data.cms.gov catalog. Published as ZIP at cms.gov research page.
        "url_override": (
            "https://www.cms.gov/files/zip/"
            "2023-chronic-conditions-chartbook-tables.zip"
        ),
        "description": "Chronic Conditions Among Medicare Beneficiaries (2023, ZIP)",
        "note": (
            "Not in data.cms.gov catalog. Published separately at cms.gov/research. "
            "ZIP contains Excel tables; CSV extraction may require manual preprocessing."
        ),
    },
    # ------------------------------------------------------------------ #
    # Claim-type / utilization summaries (no standalone PUF)              #
    # ------------------------------------------------------------------ #
    "cms_claim_type_puf": {
        # No 'Fee-for-Service Claims by Type' standalone dataset. Using the
        # Physician/Supplier Procedure Summary as the closest substitute.
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-07/"
            "bb32bbbc-6af2-4a47-9f21-fd12d2e8e9d6/"
            "Physician_Supplier_Procedure_Summary_2024.csv"
        ),
        "catalog_uuid": "164fc736-4179-4100-9f79-592b69e41975",
        "description": "Physician/Supplier Procedure Summary 2024 (substitute for claim-type PUF)",
        "note": "No standalone claim-type PUF in data.cms.gov; using Procedure Summary as substitute.",
    },
    "cms_utilization_puf": {
        # No standalone utilization PUF. Using Physician & Other Practitioners
        # by Provider and Service (the most granular utilization file available).
        "url_override": (
            "https://data.cms.gov/sites/default/files/2025-04/"
            "22edfd1e-d17a-4478-ad6b-92cac2a5a3c4/MUP_PHY_R25_P05_V20_D23_Prov.csv"
        ),
        "catalog_uuid": "8889d81e-2ee7-448f-8713-f071038289b5",
        "description": "Medicare Physician PUF by Provider (utilization proxy, DY2023)",
        "note": "No standalone utilization PUF; using Physician PUF as closest substitute.",
    },
    # ------------------------------------------------------------------ #
    # NPPES (special: stable URL pattern, separate download portal)        #
    # ------------------------------------------------------------------ #
    "cms_nppes": {
        "url_override": (
            "https://download.cms.gov/nppes/"
            "NPPES_Data_Dissemination_{month}_{year}.zip"
        ),
        "description": "NPPES NPI Registry Monthly Dissemination (ZIP → CSV)",
        "note": "URL uses {month}/{year} template. January used for annual snapshots.",
    },
}

REQUEST_TIMEOUT = 120
MAX_FILE_AGE_DAYS = 30  # Re-download if cached file is older than this


def _get_catalog(force_refresh: bool = False) -> Optional[dict]:
    """Fetch and cache data.cms.gov/data.json DCAT catalog.

    Returns the parsed catalog dict or None on failure.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not force_refresh and _CATALOG_CACHE_PATH.exists():
        age_days = (time.time() - _CATALOG_CACHE_PATH.stat().st_mtime) / 86400
        if age_days <= _CATALOG_MAX_AGE_DAYS:
            try:
                return json.loads(_CATALOG_CACHE_PATH.read_text())
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
        return catalog
    except Exception as e:
        logger.warning(f"Failed to fetch CMS DCAT catalog: {e}")
        return None


def _discover_url_from_catalog(catalog_uuid: str) -> Optional[str]:
    """Find the best CSV download URL for a dataset UUID in data.cms.gov/data.json."""
    catalog = _get_catalog()
    if not catalog:
        return None

    datasets = catalog.get("dataset", [])
    for dataset in datasets:
        identifier = dataset.get("identifier", "")
        if catalog_uuid not in identifier:
            continue
        for dist in dataset.get("distribution", []):
            media_type = dist.get("mediaType", "").lower()
            dl_url = dist.get("downloadURL", "")
            if media_type == "text/csv" or dl_url.lower().endswith(".csv"):
                return dl_url
        # Fall back to any downloadURL if no CSV found
        for dist in dataset.get("distribution", []):
            dl_url = dist.get("downloadURL", "")
            if dl_url:
                return dl_url

    logger.warning(f"UUID {catalog_uuid} not found in CMS DCAT catalog")
    return None


def _url_is_alive(url: str) -> bool:
    """Return True if a HEAD request to url succeeds (2xx or 3xx).

    Used to verify a hardcoded url_override is still valid before falling
    back to dynamic catalog discovery.
    """
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        return resp.status_code < 400
    except requests.RequestException:
        return False


def _get_download_url(source_name: str, year: int) -> Optional[str]:
    """Resolve the download URL for a CMS dataset.

    Resolution order:
    1. If url_override is present, use it — but fall back to catalog discovery
       if the override URL returns 4xx/5xx (CMS rotates paths annually).
    2. If catalog_uuid is present, look up the latest CSV in data.cms.gov/data.json.
    3. Fail with an error log.
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

    # Direct URL override — interpolate {month}/{year} for NPPES
    if "url_override" in entry:
        month = "January"
        url = entry["url_override"].format(month=month, year=year)

        # Verify the URL is still alive; CMS rotates dated file paths each year.
        # Skip the liveness check for NPPES (templated URL with month/year — always valid pattern).
        if "{month}" not in entry["url_override"] and "{year}" not in entry["url_override"]:
            if not _url_is_alive(url):
                logger.warning(
                    f"url_override for {source_name} returned 4xx/5xx ({url}). "
                    "Falling back to dynamic catalog discovery. "
                    "Update url_override in CMS_DATASET_REGISTRY with the new URL."
                )
                # Fall through to catalog discovery below
                if "catalog_uuid" in entry:
                    catalog_url = _discover_url_from_catalog(entry["catalog_uuid"])
                    if catalog_url:
                        logger.info(f"Catalog discovery resolved {source_name} → {catalog_url}")
                        return catalog_url
                return None

        return url

    # Dynamic catalog discovery via UUID (no url_override present)
    if "catalog_uuid" in entry:
        url = _discover_url_from_catalog(entry["catalog_uuid"])
        if url:
            return url

    logger.error(
        f"Cannot resolve download URL for {source_name}. "
        "Add a 'url_override' or 'catalog_uuid' entry in CMS_DATASET_REGISTRY."
    )
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
        Returns (None, False) if download failed or source is not available.
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

        # Handle zip files: extract the largest CSV
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
                # Use the largest CSV (most likely the main data file)
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
        entry = CMS_DATASET_REGISTRY[source_name]
        if entry.get("not_available"):
            logger.info(f"Skipping {source_name}: not available as standalone download")
            continue
        filepath, _ = download_cms_file(source_name, year=year, force=force)
        if filepath:
            results[source_name] = filepath
        else:
            logger.warning(f"Failed to download {source_name}")
    return results
