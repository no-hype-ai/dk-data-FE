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
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Metric is optional at import time — tests / tooling may import this module
# without the full prometheus_client stack. Fall back to a no-op if unavailable.
try:
    from dk_data.observability.metrics import DK_ARTIFACT_SIZE_MISMATCH_TOTAL
except Exception:  # pragma: no cover — defensive
    class _NoopCounter:
        def labels(self, *_, **__):
            return self

        def inc(self, *_):
            return None

    DK_ARTIFACT_SIZE_MISMATCH_TOTAL = _NoopCounter()

# Provenance writer is optional at import time — when the ingestion DB is
# unreachable (local tooling, unit tests without a DB), provenance writes
# become no-ops. Import failure here must never prevent a download; see
# plan §C.4 ("Failure in record() must NOT fail the download").
try:
    from dk_data.ingestion.common.integrity import ArtifactProvenanceWriter
except Exception:  # pragma: no cover — defensive
    ArtifactProvenanceWriter = None  # type: ignore[assignment, misc]

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

    # Hospital quality programs (HAC / HRRP / VBP)
    "cms_hac_reduction": {
        # Provider Data portal — HAC Reduction Program
        "catalog_uuid": "yq43-i98g",
        "catalog_base": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "description": "Hospital-Acquired Condition (HAC) Reduction Program",
    },
    "cms_hrrp": {
        # Provider Data portal — Hospital Readmissions Reduction Program
        "catalog_uuid": "9n3s-kdb3",
        "catalog_base": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "description": "Hospital Readmissions Reduction Program",
    },
    "cms_vbp": {
        # Provider Data portal — Hospital Value-Based Purchasing
        "catalog_uuid": "ypbt-wvdk",
        "catalog_base": "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items",
        "description": "Hospital Value-Based Purchasing (HVBP)",
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
    """Compute MD5 hash of a file.

    Retained for callers that keyed their state on the md5 digest.  New
    integrity checks use :func:`_compute_file_sha256`.
    """
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_file_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file (used for download-integrity sidecars)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(source_name: str, year: int) -> Path:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOAD_DIR / f"{source_name}_{year}.csv"


def _extract_dir(source_name: str, year: int) -> Path:
    """Per-source subdirectory used for zip extractions.

    Every extracted file from a single source+year bundle lands in this
    directory so callers can enumerate all artifacts.  The directory is
    re-created on every download to avoid stale files from prior releases.
    """
    return DOWNLOAD_DIR / f"{source_name}_{year}_extracted"


def _hash_file_path(source_name: str, year: int) -> Path:
    return DOWNLOAD_DIR / f"{source_name}_{year}.md5"


def _looks_like_zip(filename: str, content_type: str) -> bool:
    return (
        filename.lower().endswith(".zip")
        or content_type.startswith("application/zip")
        or content_type.startswith("application/x-zip")
    )


def _stream_to_file(
    resp: requests.Response, tmp_path: Path
) -> tuple[int, Optional[int]]:
    """Stream response body to ``tmp_path``.

    Returns ``(bytes_written, content_length_header)``.  ``content_length_header``
    is ``None`` when the upstream did not advertise a length (e.g. chunked
    transfer) — in that case the caller must not treat a size mismatch as an
    error because there is no source of truth.
    """
    header_value = resp.headers.get("Content-Length")
    content_length = int(header_value) if header_value and header_value.isdigit() else None

    written = 0
    with open(tmp_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                written += len(chunk)
    return written, content_length


def _attempt_download(
    url: str, tmp_path: Path, source_name: str
) -> tuple[Optional[int], Optional[int], Optional[str], dict]:
    """Single download attempt.

    Returns ``(written, content_length, content_type, headers)`` on success,
    or ``(None, None, None, {})`` on empty/network failure.  On Content-
    Length mismatch returns ``(None, content_length, content_type, headers)``
    so the caller can still log provenance for the failed attempt.  The
    caller owns deletion of ``tmp_path`` on ``None`` responses.

    ``headers`` is a plain-dict snapshot of the HTTP response headers, with
    the keys preserved as the server sent them — the integrity writer does
    a case-insensitive lookup so either casing works downstream.
    """
    try:
        resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error(f"Download failed for {source_name}: {exc}")
        return None, None, None, {}

    # Snapshot headers before we consume the body — after iter_content the
    # connection may be closed and server trailers lost.
    headers = dict(resp.headers)
    content_type = resp.headers.get("content-type", "")
    written, content_length = _stream_to_file(resp, tmp_path)

    if written == 0:
        logger.error(f"Downloaded empty file for {source_name}")
        return None, content_length, content_type, headers

    if content_length is not None and written != content_length:
        logger.warning(
            "Content-Length mismatch for %s: header=%d written=%d (url=%s)",
            source_name,
            content_length,
            written,
            url,
        )
        DK_ARTIFACT_SIZE_MISMATCH_TOTAL.labels(source=source_name).inc()
        return None, content_length, content_type, headers

    return written, content_length, content_type, headers


def _write_sidecar(
    source_name: str,
    year: int,
    primary_path: Path,
    content_length: Optional[int],
    sha256: str,
) -> None:
    """Write the ``<cache>.md5`` sidecar capturing Content-Length + SHA256.

    The name ``.md5`` is kept for compatibility with the existing 30-day cache
    convention but the body is now a multi-line document.  Legacy callers that
    read the first line unchanged still get a valid hex digest.
    """
    sidecar = _hash_file_path(source_name, year)
    md5 = _compute_file_hash(primary_path)
    lines = [md5, f"sha256={sha256}"]
    if content_length is not None:
        lines.append(f"content_length={content_length}")
    sidecar.write_text("\n".join(lines) + "\n")


def _derive_source_name_from_cache(cache_path: Path) -> str:
    """Derive a stable source_name from a cache-file path.

    The CMS cache layout puts every artifact at a path like
    ``/tmp/cms_downloads/cms_part_d_spending_2023.csv`` (or ``.zip``,
    ``.json``). For provenance grouping we want ``cms_part_d_spending`` —
    the source key, independent of year and extension. The public API
    ``download_cms_files`` receives ``source_name`` directly, so this
    helper is only used as a fallback / sanity check.
    """
    stem = cache_path.stem  # drop extension
    # Trailing _NNNN (4-digit year) is the common case. Anything else is
    # already a bare source key.
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return parts[0]
    return stem


def _record_provenance(
    *,
    source_name: str,
    source_url: str,
    local_path: Path,
    headers: dict,
    bytes_written: int,
    sha256: str,
) -> None:
    """Best-effort write to ``meta.artifact_provenance``.

    Per plan §C.4 a provenance-write failure MUST NOT fail the download —
    any exception (including the optional import itself being absent) is
    swallowed here so the caller never has to guard.
    """
    if ArtifactProvenanceWriter is None:
        return
    writer = None
    try:
        writer = ArtifactProvenanceWriter()
        writer.record_swallow(
            source_name=source_name,
            source_url=source_url,
            local_path=str(local_path),
            headers_dict=headers,
            bytes_written=bytes_written,
            sha256=sha256,
        )
    except Exception as exc:  # noqa: BLE001 — defensive, record_swallow is already non-raising
        logger.warning(
            "Provenance writer could not be constructed for %s (%s); continuing",
            source_name,
            exc,
        )
    finally:
        if writer is not None:
            writer.close()


def _extract_all(zip_path: Path, target_dir: Path) -> list[Path]:
    """Extract every member of ``zip_path`` into ``target_dir``.

    Replaces the legacy "largest CSV wins" behaviour that silently discarded
    every other file in a multi-file bundle (see plan §A.1 / §B.4 — NPPES).
    Returns the list of absolute paths actually written (directories are
    skipped).  Zip-slip is defended against via ``Path.resolve`` comparison.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_target = target_dir.resolve()
    extracted: list[Path] = []

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            dest = (target_dir / info.filename).resolve()
            try:
                dest.relative_to(resolved_target)
            except ValueError:
                raise RuntimeError(
                    f"Refusing to extract {info.filename!r}: escapes target "
                    f"directory {target_dir}"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                for chunk in iter(lambda: src.read(65536), b""):
                    out.write(chunk)
            extracted.append(dest)

    return extracted


def download_cms_file(
    source_name: str,
    year: int = 2023,
    force: bool = False,
) -> tuple[Optional[str], bool]:
    """Download a CMS bulk file for the given source and year.

    Returns ``(filepath, was_new)``.  ``filepath`` is the local path to the
    primary file — for plain CSV downloads that is the downloaded file; for
    zip bundles it is the *largest* extracted member (legacy behaviour for
    callers that only handle one file).  *All* files inside the zip are
    extracted to :func:`_extract_dir` and can be enumerated via
    :func:`download_cms_files`.  ``was_new`` is ``True`` when the download
    actually ran, ``False`` when cache was reused.  Returns ``(None, False)``
    on failure or when the source is not publicly available.

    Backwards-compatible with callers that expect a single-path return.  To
    access every extracted file (e.g. NPPES multi-file zips) call
    :func:`download_cms_files` instead.
    """
    paths, was_new = download_cms_files(source_name, year=year, force=force)
    if not paths:
        return None, False
    return str(paths[0]), was_new


def download_cms_files(
    source_name: str,
    year: int = 2023,
    force: bool = False,
) -> tuple[list[Path], bool]:
    """Download a CMS bulk file and return *every* artifact it produces.

    For plain CSV/JSON downloads this returns a single-element list.  For
    ``.zip`` downloads this returns every file extracted from the bundle,
    ordered so the largest file is first (legacy primary-path convention).

    Behaviour vs :func:`download_cms_file`:
      * single-file callers can keep using ``download_cms_file`` unchanged
      * multi-file callers get the full list, which is the new baseline for
        plan §B.4 (fix truncation at zip extraction)

    Content-Length integrity is enforced on every attempt.  On mismatch the
    partial ``.tmp`` is deleted, a warning logged, and the download is retried
    once.  A second mismatch fails loudly (returns ``([], False)``) and the
    ``dk_artifact_size_mismatch_total{source}`` counter is incremented for
    each failed attempt.
    """
    cache_path = _cache_path(source_name, year)
    extract_dir = _extract_dir(source_name, year)

    # Cache hit — return the primary file plus any previously-extracted siblings.
    if not force and cache_path.exists():
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400
        if age_days <= MAX_FILE_AGE_DAYS:
            logger.info(
                f"Using cached {source_name} file (age: {age_days:.1f}d): {cache_path}"
            )
            cached: list[Path] = [cache_path]
            if extract_dir.exists():
                for p in sorted(extract_dir.rglob("*")):
                    if p.is_file() and p.resolve() != cache_path.resolve():
                        cached.append(p)
            return cached, False

    url = _get_download_url(source_name, year)
    if not url:
        logger.error(f"Cannot determine download URL for {source_name} year={year}")
        return [], False

    logger.info(f"Downloading {source_name} year={year} from {url}")

    tmp_path = cache_path.with_suffix(".tmp")

    headers: dict = {}
    for attempt in (1, 2):
        written, content_length, content_type, headers = _attempt_download(
            url, tmp_path, source_name
        )
        if written is not None:
            break
        tmp_path.unlink(missing_ok=True)
        if attempt == 1:
            logger.info("Retrying %s after failed download attempt", source_name)
        else:
            logger.error(
                "Download failed twice for %s (content-length or empty); giving up",
                source_name,
            )
            return [], False

    try:
        filename = urlparse(url).path.split("/")[-1]
        is_zip = _looks_like_zip(filename, content_type or "")

        if is_zip:
            # Re-create the extraction directory so stale files from previous
            # releases cannot leak through.
            if extract_dir.exists():
                for p in sorted(extract_dir.rglob("*"), reverse=True):
                    if p.is_file():
                        p.unlink(missing_ok=True)
                    elif p.is_dir():
                        p.rmdir()
                extract_dir.rmdir()

            try:
                extracted = _extract_all(tmp_path, extract_dir)
            except zipfile.BadZipFile as exc:
                logger.error(f"Corrupt ZIP for {source_name}: {exc}")
                tmp_path.unlink(missing_ok=True)
                return [], False

            if not extracted:
                logger.error(f"ZIP contained no extractable files for {source_name}")
                tmp_path.unlink(missing_ok=True)
                return [], False

            # Pick primary = largest file (historical convention for single-
            # path callers).  Every other file is still returned in the list.
            extracted.sort(key=lambda p: p.stat().st_size, reverse=True)
            primary_src = extracted[0]

            # Copy (not move) the primary into the legacy cache_path so single-
            # file callers keep finding it at the old location, while the
            # extracted directory remains the source of truth for everyone.
            cache_path.write_bytes(primary_src.read_bytes())
            tmp_path.unlink(missing_ok=True)

            sha256 = _compute_file_sha256(cache_path)
            _write_sidecar(source_name, year, cache_path, content_length, sha256)
            _record_provenance(
                source_name=source_name,
                source_url=url,
                local_path=cache_path,
                headers=headers,
                bytes_written=cache_path.stat().st_size,
                sha256=sha256,
            )

            total_bytes = sum(p.stat().st_size for p in extracted)
            logger.info(
                "Downloaded %s year=%d: %d files, %.1f MB total, sha256=%s",
                source_name,
                year,
                len(extracted),
                total_bytes / 1024 / 1024,
                sha256[:12],
            )
            # Primary first, then the rest (including primary's sibling copy).
            return [cache_path, *[p for p in extracted if p != primary_src]], True

        # Plain (non-zip) download.
        tmp_path.rename(cache_path)
        sha256 = _compute_file_sha256(cache_path)
        _write_sidecar(source_name, year, cache_path, content_length, sha256)
        _record_provenance(
            source_name=source_name,
            source_url=url,
            local_path=cache_path,
            headers=headers,
            bytes_written=cache_path.stat().st_size,
            sha256=sha256,
        )
        logger.info(
            "Downloaded %s year=%d: %.1f MB, sha256=%s",
            source_name,
            year,
            cache_path.stat().st_size / 1024 / 1024,
            sha256[:12],
        )
        return [cache_path], True

    except Exception as exc:
        logger.error(f"Unexpected error processing download for {source_name}: {exc}")
        tmp_path.unlink(missing_ok=True)
        return [], False


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
