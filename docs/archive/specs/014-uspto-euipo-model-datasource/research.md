# Research: USPTO & EUIPO Model Datasource Integration

**Feature**: 014-uspto-euipo-model-datasource
**Date**: 2026-02-16

## 1. Issue Context

### GitHub Issue dk-data#143

- **Title**: "USPTO should be reorganized to use the model datasource"
- **Comment**: "@PhilippSchloz - can you work with @lanhel to get USPTO and EUIPO integrated into dk-data-fe please."
- **Assignees**: @lanhel, @PhilippSchloz

### Related Issues (dk-data repo)

| Issue | Title | Status |
|-------|-------|--------|
| #143 | USPTO should be reorganized to use the model datasource | Open |
| #424 | Migrate EUIPO ETL + Database Schema | Open |
| #422 | Phase 2.2: Migrate USPTO ETL + Database Schema | Closed |
| #436 | Migrate USPTO Fast Track Datasource | Open |
| #419 | Epic: Complete ETL Datasource Migration | Open |

## 2. Existing USPTO Architecture in dk-data-FE

### Two Separate Fetcher Pipelines

The current implementation has two independent USPTO fetchers that were created during feature 011-datasource-integration:

#### USPTO CI (Competitive Intelligence)
- **API**: PatentSearch API (public, no auth required)
- **Endpoint**: `https://search.patentsview.org/api/v1/patent/` (POST with JSON body)
- **Query scope**: Search terms from `meta.ci_search_terms` table + CPC codes A61K, A61P, C07D
- **Refresh**: Weekly (Sunday 14:00 UTC)
- **Raw table**: `raw.uspto_ci` (patent_id PK)
- **Loader**: Direct INSERT via `sources/uspto_ci.py`

#### USPTO Patents (Credential-Gated)
- **API**: PatentSearch API (with API key for higher rate limits)
- **Endpoint**: `https://search.patentsview.org/api/v1/patent/` (POST with JSON body)
- **Query scope**: CPC code filter only (no search term scoping)
- **Refresh**: Weekly (Sunday 17:00 UTC)
- **Raw table**: `raw.uspto_patents` (patent_number PK)
- **Loader**: Direct INSERT via `sources/uspto_patents.py`

### Key Architectural Observation

Both USPTO fetchers hit the same PatentSearch API but with different query strategies and different raw table schemas. Both use POST with JSON body and cursor-based pagination (size/after). The legacy PatentsView API at `api.patentsview.org` was discontinued in May 2025 (returns 410 Gone).

### SQLMesh Model Status

| Model | Exists? | Source | Notes |
|-------|---------|--------|-------|
| `bronze.uspto_patents` | YES | `raw.uspto_patents` | Extracts from `response_body->'patents'` JSONB |
| `bronze.uspto_ci` | NO | — | Missing entirely |
| `bronze.epo_patents` | NO | — | Missing entirely |
| `silver.patents` | YES | `bronze.drugbank` only | Does NOT read from any USPTO or EPO bronze tables |

### Critical Gap

The `bronze.uspto_patents` model reads from `raw.uspto_patents` but expects data in `raw.api_responses` format (with `response_body` JSONB column). However, the actual `raw.uspto_patents` table has flat columns (patent_number, title, abstract, etc.) — not a JSONB response body. This means the existing bronze model may be non-functional.

**The USPTO Patents loader writes individual records directly to flat raw table columns**, but the bronze SQLMesh model tries to parse JSONB `response_body->'patents'` from `raw.uspto_patents`. This is the core "reorganization" issue referenced in #143.

### Resolution Options

1. **Refactor loaders** to write raw API responses as JSONB into `raw.api_responses` (generic table) — then let SQLMesh extract fields
2. **Refactor bronze models** to read from the flat raw tables (current schema) — simpler, preserves existing data
3. **Hybrid**: Keep flat raw tables but create bronze models that transform flat -> typed bronze

**Recommendation**: Option 2 (refactor bronze models to read flat raw tables). This preserves all existing data and requires no loader changes.

## 3. EPO OPS Architecture

### Current State

- **API**: EPO Open Patent Services REST API v3.2
- **Auth**: OAuth2 client_credentials (`EPO_CONSUMER_KEY` + `EPO_CONSUMER_SECRET`)
- **Data format**: XML (parsed to dicts in fetcher)
- **Raw table**: `raw.epo_patents` (publication_id PK)
- **Loader**: `sources/epo_ops.py` -> `raw.epo_patents`
- **Bronze model**: MISSING
- **Silver model**: NOT wired into `silver.patents`

## 4. USPTO Trademark API Research (Verified from Official Docs)

### Overview

There are **four distinct systems** for accessing USPTO trademark data. None offer a single "search all trademarks by Nice Class" REST endpoint.

### 4.1 TSDR Data API (Primary REST API)

- **API Name**: TSDR REST API v1.0
- **Base URL**: `https://tsdrapi.uspto.gov/`
- **Swagger/OpenAPI Spec**: `https://developer.uspto.gov/sites/default/files/2023-03/swagger_v1.json`
- **Documentation**: `https://developer.uspto.gov/api-catalog/tsdr-data-api`

**Authentication**: API Key (required since October 2, 2020)
- Register at `https://account.uspto.gov/api-manager/` (requires MyUSPTO account)
- Support: `APIhelp@uspto.gov`

**Rate Limits** (from official FAQ):
- Standard requests: **60 requests per API key per minute**
- PDF/ZIP/multi-case: **4 requests per API key per minute**

**Key Endpoints**:
- `GET /ts/cd/casestatus/{caseid}/info` — Case status (ST96 XML)
- `GET /ts/cd/caseMultiStatus/{type}?ids=...` — **Batch lookup** (JSON) — best for ETL
- `GET /last-update/info.json?sn=XXXXXXXX` — Check if case updated since last run

**Case ID formats**: `sn` + 8 digits (serial), `rn` + 7 digits (registration)

**Limitation**: TSDR is a **lookup-only API** — you must know the serial/registration number. There is no "search all Nice Class 5" endpoint.

**Response Data Model** (from Swagger `Trademark` object):
- `serialNumber`, `filingDate`, `usRegistrationNumber`, `usRegistrationDate`
- `status` (integer code), `statusStr`, `statusDate`
- `markElement` (mark text), `descOfMark`, `markType`
- `trademark`/`serviceMark`/`certificationMark`/`collectiveMembershipMark` (boolean flags)
- `parties.currentOwners[].name`, `entityType`, `address`, `city`, `citizenship`
- `gsList[].internationalClasses[]` (**Nice classes**), `usClasses[]`, `description`
- `gsList[].firstUseDate`, `firstUseInCommerceDate`
- `prosecutionHistory[]`, `assignments[]`, `proceedings[]`

### 4.2 USPTO Bulk Data (XML Downloads)

- **Legacy URL**: `https://bulkdata.uspto.gov/` (being decommissioned)
- **New location**: `https://data.uspto.gov/` (Open Data Portal)

Provides daily XML files (ST96 format) containing ALL trademark data. This is the only way to get a comprehensive Class 5 dataset.

**Key XML fields**: `ClassNumber` = "005", `MarkVerbalElementText`, `ApplicationNumber`, `RegistrationNumber`, `MarkCurrentStatusCode`, `ApplicationDate`, `ApplicantBag`

### 4.3 New Open Data Portal (data.uspto.gov)

- **URL**: `https://data.uspto.gov/`
- **Swagger**: `https://data.uspto.gov/swagger/index.html`
- **Status**: Live, actively migrating from legacy. Angular SPA. PTAB API v3 already migrated. Trademark APIs migration planned.

### 4.4 TESS (Trademark Electronic Search System)

- **URL**: `https://tmsearch.uspto.gov/`
- **Status**: Web-only CGI-based system. **NO REST API**. Terms of Use prohibit automated scraping.
- Supports full-text search, Nice class filtering, status filtering — but only via browser.

### Recommended Approach for dk-data-FE

**Hybrid: Bulk Data + TSDR API**

1. **Initial load**: Download Trademark Daily XML files from `data.uspto.gov`, parse for Class 005, load to `raw.uspto_trademarks`
2. **Weekly incremental**: Use TSDR API `/ts/cd/caseMultiStatus/sn?from=...&to=...` to sweep serial number ranges for updates
3. **Change detection**: Use `/last-update/info.json` to efficiently detect which cases changed

**Doppler secrets needed**: `USPTO_TSDR_API_KEY`

## 5. EUIPO API Research (Verified from Official Docs)

### Overview

EUIPO does **NOT** have an official, publicly documented REST API in the traditional sense. The available options are:

### 5.1 eSearch Plus (Web Application — NOT an API)

- **URL**: `https://euipo.europa.eu/eSearch/`
- **Nature**: Browser-based SPA. The underlying XHR endpoints are **undocumented internal APIs**.
- EUIPO does NOT publish an official "eSearch API" for programmatic use.
- `https://api.euipo.europa.eu` returns HTTP 404.
- `/en/api-gateway` returns "Not found".

### 5.2 EUIPO API Gateway (IBM API Connect)

- **Platform**: IBM API Connect (API management)
- **Access**: Requires registration as a developer. Not publicly open.
- **Authentication**: IBM Client ID + Client Secret
- API "products" are gated — must request access individually.
- The dk-data backend uses this gateway (from code analysis: `api.euipo.europa.eu/trademark-search` with IBM Client ID headers), but the external docs confirm `api.euipo.europa.eu` returns 404 for unauthenticated requests.

### 5.3 TMview API (Best Option — Federated Search)

TMview is EUIPO's federated trademark search system covering 70+ IP offices.

- **Base URL**: `https://www.tmdn.org/tmview/api/search`
- **Request**: POST with JSON body
- **Response**: JSON
- **Authentication**: Registration at TMview portal. Some endpoints semi-public.

**Example request**:
```json
POST https://www.tmdn.org/tmview/api/search
Content-Type: application/json

{
  "pageSize": 100,
  "pageIndex": 1,
  "criteria": {
    "tradeMarkName": "",
    "niceClasses": ["05"],
    "tradeMarkOffices": ["EM"],
    "tradeMarkStatus": ["Filed", "Registered"],
    "applicationDateFrom": "2025-01-01",
    "applicationDateTo": "2025-12-31"
  }
}
```

**Response fields**:
- `applicationNumber`, `registrationNumber`
- `tradeMarkName`, `tradeMarkType` (Word, Figurative, 3D, Sound, etc.)
- `niceClasses[]`, `applicationDate`, `registrationDate`, `expiryDate`
- `status` (Filed, Registered, Refused, Withdrawn, etc.)
- `applicantName`, `applicantCountry`
- `representativeName`
- `imageURL` (for figurative marks)
- `goodsAndServices` (text per Nice class)

**Pagination**: `pageIndex` (1-based) + `pageSize`

### 5.4 EU Open Data Portal (Bulk Downloads)

- **URL**: `https://data.europa.eu/data/datasets?catalog=euipo`
- Provides CSV/XML bulk downloads of EUIPO trademark registrations.

### 5.5 EUIPO Internal API (from dk-data backend code — use with caution)

The dk-data backend successfully uses these endpoints (from code review):
- **API**: `https://api.euipo.europa.eu/trademark-search`
- **Auth**: OAuth2 client credentials via `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`
- **Headers**: `X-IBM-Client-Id` required

**However**: External verification shows `api.euipo.europa.eu` returns 404 without authentication. This endpoint requires IBM API Connect developer registration, which is a gated process.

### Recommended Approach for dk-data-FE

**Option A (Recommended): TMview API**
- Use `https://www.tmdn.org/tmview/api/search` with Nice Class 05 filter
- POST JSON, paginate through results
- Filter by `tradeMarkOffices: ["EM"]` for EU trademarks specifically
- Register for TMview API access

**Option B: IBM API Gateway (if already registered)**
- If dk-data already has IBM Client ID credentials, reuse them via Doppler
- Use `api.euipo.europa.eu/trademark-search` with OAuth2 + IBM Client ID
- Secrets: `EUIPO_API_KEY`, `EUIPO_SECRET_KEY`

**Option C: EU Open Data Portal bulk download**
- Download CSV/XML from `data.europa.eu`
- Parse locally for Nice Class 5
- Lower frequency but complete dataset

### Nice Classification Filter

For pharmaceutical relevance, filter by:
- **Class 5**: Pharmaceutical and veterinary preparations
- **Class 10**: Surgical, medical, dental and veterinary apparatus
- **Class 42**: Scientific and technological services (drug discovery)
- **Class 44**: Medical services

### Data Volume Estimates

- Total EUTMs in Class 5: ~200,000+
- Weekly delta (new filings + status changes): ~500-2,000 records
- Initial historical backfill: ~10,000 records (last 2 years, Class 5 only)

## 5a. dk-data Backend Cross-Reference

### Key Differences: dk-data vs dk-data-FE

| Aspect | dk-data (Backend) | dk-data-FE (Frontend Engineering) |
|--------|-------------------|-----------------------------------|
| **USPTO Data** | Trademarks (BDSS bulk XML) + Patents | Patents (PatentsView API) + Trademarks (TSDR/Bulk) |
| **EUIPO Access** | IBM API Gateway (gated) | TMview API or IBM Gateway (TBD) |
| **Architecture** | Monolithic ETL packages | Medallion: raw->bronze->silver->gold via SQLMesh |

### Reusable Patterns from dk-data (verify against external docs)

1. **EUIPO data model enums** — MarkKind, MarkFeature, Status values (validate against TMview response)
2. **EUIPO pagination pattern** — sort by `applicationNumber:asc`
3. **USPTO XML parsing** — ST96 XML structure for bulk data ingestion

## 5. Medallion Architecture Integration

### Data Flow After Implementation

```
PATENTS:
USPTO PatentsView API ──> raw.uspto_patents ──> bronze.uspto_patents ──┐
                                                                       │
USPTO PatentsView API ──> raw.uspto_ci ──> bronze.uspto_ci ────────────┤
                                                                       ├──> silver.patents
EPO OPS API ──────────> raw.epo_patents ──> bronze.epo_patents ────────┤
                                                                       │
DrugBank ─────────────> bronze.drugbank ──> (patents array extraction) ─┘
                                                   │
                                                   └──> gold.lifecycle_evidence
                                                   └──> gold.molecule_profile

TRADEMARKS:
USPTO TSDR API + ─────> raw.uspto_trademarks ──> bronze.uspto_trademarks ──┐
  Bulk XML Data                                                             │
                                                                            ├──> silver.trademarks
TMview/EUIPO API ────> raw.euipo_trademarks ──> bronze.euipo_trademarks ───┘
                                                                                │
                                                                                └──> gold.molecule_profile (IP section)
```

### Silver Patents: UNION Strategy

```sql
-- CTE 1: DrugBank patents (existing)
WITH drugbank_patents AS (...)

-- CTE 2: USPTO Patents (NEW)
, uspto_patents AS (
    SELECT patent_number, title, abstract, filing_date, grant_date,
           assignee_organization AS assignee, inventors,
           cpc_codes, num_claims, 'uspto_patents' AS source
    FROM bronze.uspto_patents
    WHERE processed_to_silver = FALSE
)

-- CTE 3: USPTO CI (NEW)
, uspto_ci AS (
    SELECT patent_id AS patent_number, title, abstract, filing_date, grant_date,
           (assignees->0->>'org') AS assignee, inventors,
           cpc_codes, claims_count AS num_claims, 'uspto_ci' AS source
    FROM bronze.uspto_ci
    WHERE processed_to_silver = FALSE
)

-- CTE 4: EPO Patents (NEW)
, epo_patents AS (
    SELECT publication_id AS patent_number, title, abstract, filing_date,
           publication_date AS grant_date,
           (applicants->0) AS assignee, inventors,
           ipc_codes AS cpc_codes, NULL AS num_claims, 'epo_ops' AS source
    FROM bronze.epo_patents
    WHERE processed_to_silver = FALSE
)

-- UNION ALL with deduplication via DISTINCT ON
SELECT DISTINCT ON (patent_number) * FROM (
    SELECT * FROM drugbank_patents
    UNION ALL SELECT * FROM uspto_patents
    UNION ALL SELECT * FROM uspto_ci
    UNION ALL SELECT * FROM epo_patents
) combined
ORDER BY patent_number, source_priority
```

## 6. Testing Strategy

### Existing Test Pattern (from test_epo_ops_fetcher.py)

```python
# 1. Mock HTTP with `responses` library
@responses.activate
def test_fetch_success(self, tmp_path):
    responses.add(responses.GET, API_URL, json=MOCK_RESPONSE, status=200)
    fetcher = SomeFetcher(data_dir=str(tmp_path))
    result = fetcher.fetch(...)
    assert result["status"] == "success"

# 2. Pydantic validation tests
def test_valid_record(self):
    record = SomeRecord(required_field="value")
    assert record.required_field == "value"

def test_invalid_record(self):
    with pytest.raises(ValidationError):
        SomeRecord(required_field="")
```

### EUIPO Test Plan

- 7 fetcher tests (init, URL, success, empty, error, pagination, rate limiting)
- 5 validator tests (valid full, valid minimal, empty PK, missing PK, whitespace PK)
- Total: ~12 tests

### CI/CD

The `.github/workflows/ci.yaml` runs:
1. `ruff check .` — linting
2. `pytest tests/ -v --tb=short` — tests with PostgreSQL service container
3. `kubectl kustomize k8s/overlays/staging` — manifest validation

All new test files will be auto-discovered by pytest.

## 7. Doppler Secret Inventory

### Existing (no changes needed)

| Secret | Used By | Status |
|--------|---------|--------|
| `USPTO_API_KEY` | fetch-uspto-patents CronJob | Already in Doppler |
| `PATENTSVIEW_API_KEY` | Alternate name for same | Already in Doppler |
| `EPO_CONSUMER_KEY` | fetch-epo CronJob | Already in Doppler |
| `EPO_CONSUMER_SECRET` | fetch-epo CronJob | Already in Doppler |

### New

| Secret | Used By | Required? |
|--------|---------|-----------|
| `USPTO_TSDR_API_KEY` | fetch-uspto-trademarks CronJob | Yes — TSDR API key from `account.uspto.gov/api-manager/` |
| `EUIPO_API_KEY` | fetch-euipo CronJob | Yes — IBM Client ID or TMview API key |
| `EUIPO_SECRET_KEY` | fetch-euipo CronJob | Conditional — required if using IBM API Gateway |

## 8. Metrics Integration Points

### Current gaps in `metrics.py`

1. **`local_sources` dict** (line ~428): Missing all patent/trademark sources
2. **`raw_sources` dict** (line ~528): Missing USPTO/EPO/EUIPO for unprocessed count
3. **`layer_tables['raw']`** (line ~586): Missing patent raw tables
4. **`layer_tables['bronze']`** (line ~589): Missing patent bronze tables
5. **`layer_tables['silver']`** (line ~593): Missing `trademarks` table
6. **`external_sources` list** (line ~491): Already has `patentsview` and `ema`, need to add `euipo`

### Prometheus Metric Labels After Fix

```
dk_source_health_status{source="uspto_patents"} 1
dk_source_health_status{source="uspto_ci"} 1
dk_source_health_status{source="epo_patents"} 1
dk_source_health_status{source="euipo_trademarks"} 1
dk_raw_unprocessed_total{source="uspto_patents"} 0
dk_raw_unprocessed_total{source="euipo_trademarks"} 0
dk_table_record_count{layer="raw",table_name="uspto_patents"} 1234
dk_table_record_count{layer="bronze",table_name="euipo_trademarks"} 567
```
