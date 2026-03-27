# CMS Data Access Strategy

## Problem Statement

Our current CMS data fetchers are returning HTML error pages instead of CSV data. The CMS data portal has updated their API structure, and we need to align our fetchers with the current API specification.

## Recommended Approach

### Phase 1: Update Dataset Discovery (Priority: High)

Use the CMS data catalog (`data.json`) to dynamically discover dataset identifiers and download URLs rather than hardcoding them.

```
GET https://data.cms.gov/data.json
```

This returns DCAT-format metadata with:
- Dataset UUIDs (identifiers)
- Distribution URLs (CSV, ZIP, API endpoints)
- Last modified dates
- Schema information

**Implementation:**
```python
# Add to ingestion/fetchers/base.py
CMS_CATALOG_URL = "https://data.cms.gov/data.json"

def get_cms_dataset_info(dataset_title: str) -> dict:
    """Fetch dataset metadata from CMS catalog."""
    response = requests.get(CMS_CATALOG_URL)
    catalog = response.json()

    for dataset in catalog.get('dataset', []):
        if dataset_title.lower() in dataset.get('title', '').lower():
            return {
                'identifier': dataset.get('identifier'),
                'modified': dataset.get('modified'),
                'distributions': dataset.get('distribution', [])
            }
    return None
```

### Phase 2: API-Based Fetching (Priority: High)

Update fetchers to use the correct API endpoint structure:

| Endpoint Type | URL Pattern | Use Case |
|---------------|-------------|----------|
| Data API | `https://data.cms.gov/data-api/v1/dataset/{UUID}/data` | JSON data with pagination |
| Data Viewer | `https://data.cms.gov/data-api/v1/dataset/{UUID}/data-viewer` | JSON:API with metadata |
| Direct Download | From `distribution` array in data.json | CSV/ZIP bulk downloads |

**Key Parameters:**
- `size`: Rows per request (max 5,000, default 1,000)
- `offset`: Pagination offset
- `filter[field]=value`: Field filtering

### Phase 3: Hybrid Download Strategy

#### For Initial Bulk Load (Recommended)
Use direct CSV/ZIP downloads from the `distribution` array:

```python
def get_bulk_download_url(dataset_info: dict, format: str = 'csv') -> str:
    """Get direct download URL for bulk data."""
    for dist in dataset_info.get('distributions', []):
        media_type = dist.get('mediaType', '')
        if format == 'csv' and 'csv' in media_type:
            return dist.get('downloadURL')
        if format == 'zip' and 'zip' in media_type:
            return dist.get('downloadURL')
    return None
```

#### For Incremental Updates
Use API with pagination and filtering:

```python
def fetch_cms_api_paginated(dataset_id: str, filters: dict = None) -> list:
    """Fetch data from CMS API with pagination."""
    base_url = f"https://data.cms.gov/data-api/v1/dataset/{dataset_id}/data"
    size = 5000  # Maximum allowed
    offset = 0
    all_records = []

    while True:
        params = {'size': size, 'offset': offset}
        if filters:
            for key, value in filters.items():
                params[f'filter[{key}]'] = value

        response = requests.get(base_url, params=params)
        if response.status_code != 200:
            break

        data = response.json()
        records = data if isinstance(data, list) else data.get('data', [])

        if not records:
            break

        all_records.extend(records)
        offset += size

        # Safety limit
        if offset > 1_000_000:
            break

    return all_records
```

## Dataset-Specific Configuration

### Medicare Inpatient Hospitals

**Current Issue:** URL returns error page
**Dataset Title:** "Medicare Inpatient Hospitals - by Provider and Service"
**Recommended Approach:** API with DRG filter

```python
# Filter for TAVR DRG codes only
filters = {
    'Rndrng_Prvdr_RUCA_Desc': None,  # All providers
    # DRG 266: TAVR w/ MCC, DRG 267: TAVR w/o MCC
}

# Use JSONAPI filter syntax for DRG codes
params = {
    'filter[DRG_Cd][condition][path]': 'DRG_Cd',
    'filter[DRG_Cd][condition][operator]': 'IN',
    'filter[DRG_Cd][condition][value][]': ['266', '267']
}
```

### Hospital General Information

**Current Issue:** URL returns error page
**Dataset Title:** "Hospital General Information"
**Recommended Approach:** Bulk CSV download (small dataset ~7,000 rows)

```python
# Lookup from data.json, then direct download
dataset_info = get_cms_dataset_info("Hospital General Information")
csv_url = get_bulk_download_url(dataset_info, 'csv')
```

### Cost Reports (HCRIS)

**Current Issue:** Not fetching
**Dataset Title:** "Hospital Cost Report" or search for "HCRIS"
**Recommended Approach:** ZIP download (large dataset)

```python
# Cost reports are large - use ZIP download
dataset_info = get_cms_dataset_info("Hospital Cost Report")
zip_url = get_bulk_download_url(dataset_info, 'zip')
```

## Implementation Plan

### Step 1: Create CMS Catalog Service
Create `ingestion/services/cms_catalog.py`:
- Cache `data.json` locally (refresh daily)
- Provide lookup functions for datasets
- Return distribution URLs

### Step 2: Update Fetchers
Modify each fetcher to:
1. First check local cache for dataset metadata
2. Fall back to fetching from `data.json`
3. Use distribution URLs for downloads
4. Log dataset versions for audit

### Step 3: Add Fallback Logic
```python
def fetch_with_fallback(dataset_title: str):
    """Try multiple methods to fetch data."""
    dataset_info = get_cms_dataset_info(dataset_title)

    # Method 1: Try bulk CSV download
    csv_url = get_bulk_download_url(dataset_info, 'csv')
    if csv_url:
        try:
            return download_csv(csv_url)
        except Exception as e:
            logger.warning(f"CSV download failed: {e}")

    # Method 2: Try API with pagination
    try:
        return fetch_cms_api_paginated(dataset_info['identifier'])
    except Exception as e:
        logger.warning(f"API fetch failed: {e}")

    # Method 3: Try ZIP download
    zip_url = get_bulk_download_url(dataset_info, 'zip')
    if zip_url:
        return download_and_extract_zip(zip_url)

    raise DataFetchError(f"All methods failed for {dataset_title}")
```

### Step 4: Add Monitoring
- Log successful dataset versions
- Alert on consecutive failures
- Track data freshness in `meta.data_sources`

## API Rate Limiting

CMS does not publish explicit rate limits, but recommended practices:
- Add 100ms delay between paginated requests
- Use exponential backoff on 429 responses
- Limit concurrent connections to 2-3

## Testing Strategy

1. **Unit Tests:** Mock API responses
2. **Integration Tests:** Fetch small datasets (< 1,000 rows)
3. **Smoke Tests:** Verify `data.json` accessibility daily

## Resources

| Resource | URL |
|----------|-----|
| Data Portal | https://data.cms.gov |
| API Documentation | https://data.cms.gov/api-docs |
| Data Catalog (JSON) | https://data.cms.gov/data.json |
| API Guide PDF | https://data.cms.gov/sites/default/files/2024-10/API%20Guide%20Formatted%201_6.pdf |
| Support Email | data.support@cms.hhs.gov |

## Next Steps

1. [ ] Create `cms_catalog.py` service module
2. [ ] Update `CMSInpatientFetcher` with new approach
3. [ ] Update `CMSHospitalInfoFetcher` with new approach
4. [ ] Update `CMSCostReportsFetcher` with new approach
5. [ ] Add integration tests
6. [ ] Update job definitions with retry logic
7. [ ] Document dataset identifiers in config
