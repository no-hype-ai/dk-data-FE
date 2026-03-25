# Quickstart: Data Source Integration

**Feature**: 011-datasource-integration
**Date**: 2026-02-14

## Overview

This feature adds 33 data sources in two tracks:
1. **Molecule sources (Tier 2A/3)**: Config-only — extend existing CronJobs, add seed SQL + catalog metadata
2. **CI sources (Tier 4)**: Full implementation — fetcher, loader, validator, raw tables, CronJob, tests

## Track 1: Enable Molecule Sources (Tier 2A/3)

### What Already Exists

All 13 molecule sources have complete `RawIngestionService` subclasses in `raw_ingestion.py`:

| Source | Class | Refresh | Target CronJob |
|--------|-------|---------|----------------|
| BindingDB | `BindingDBIngestion` | monthly | mol-fetch-monthly (new) |
| Orange Book | `OrangeBookIngestion` | weekly | mol-fetch-weekly (extend) |
| SIDER | `SIDERIngestion` | monthly | mol-fetch-monthly (new) |
| TDC ADMET | `TDCAdmetIngestion` | monthly | mol-fetch-monthly (new) |
| EMA | `EMAIngestion` | weekly | mol-fetch-weekly (extend) |
| RxNorm | `RxNormIngestion` | weekly | mol-fetch-monthly (new) |
| DailyMed | `DailyMedIngestion` | weekly | mol-fetch-monthly (new) |
| FDA Drugs | `FDADrugsIngestion` | weekly | mol-fetch-monthly (new) |
| KEGG Drug | `KEGGDrugIngestion` | monthly | mol-fetch-monthly (new) |
| TTD | `TTDIngestion` | monthly | mol-fetch-monthly (new) |
| PharmGKB | `PharmGKBIngestion` | monthly | mol-fetch-monthly (new) |
| IMGT | `IMGTIngestion` | monthly | mol-fetch-monthly (new) |
| CDC Vaccines | `CDCVaccinesIngestion` | monthly | mol-fetch-monthly (new) |

### Steps to Enable Each

1. **Extend mol-fetch-weekly CronJob** (`k8s/base/ingestion/cronjob-mol-fetch-weekly.yaml`):
   - Add `ema,orange_book` to the `--source` argument

2. **Create mol-fetch-monthly CronJob** (`k8s/base/ingestion/cronjob-mol-fetch-monthly.yaml`):
   - Schedule: `0 8 1 * *` (1st of month, 8 AM UTC)
   - Sources: `bindingdb,sider,tdc_admet,kegg_drug,ttd,pharmgkb,imgt,cdc_vaccines,uniprot,rxnorm,dailymed,fda_drugs`

3. **Add seed SQL entries** to `seed_data_sources.sql` and `seed_batch_jobs.sql`

4. **Add SOURCE_METADATA** to `catalog_refresh.py` for all 13 sources

5. **Verify** by triggering manually:
   ```bash
   kubectl create job test-mol-monthly-$(date +%s) \
     --from=cronjob/mol-fetch-monthly -n dk-data-prod
   ```

## Track 2: Implement CI Sources (Tier 4)

### Pattern: BaseFetcher + Loader + Validator

Each CI source follows this implementation pattern:

#### 1. Fetcher (`src/dk_data/ingestion/fetchers/<source>.py`)

```python
from dk_data.ingestion.fetchers.base import BaseFetcher

class PubMedFetcher(BaseFetcher):
    SOURCE_NAME = "pubmed"
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def get_latest_url(self):
        return f"{self.BASE_URL}/esearch.fcgi"

    def fetch(self, **kwargs):
        # Implement API calls with pagination
        # Return: {status, records, hash, error}
        pass
```

#### 2. Validator (`src/dk_data/ingestion/utils/validators.py`)

```python
from pydantic import BaseModel, field_validator

class PubMedRecord(BaseModel):
    pmid: str
    title: str
    abstract: str | None = None
    # ... fields matching raw.pubmed table

    @field_validator('pmid')
    @classmethod
    def validate_pmid(cls, v):
        if not v.isdigit():
            raise ValueError('PMID must be numeric')
        return v
```

#### 3. Loader (`src/dk_data/ingestion/sources/<source>.py`)

```python
def load_pubmed_data(records, **kwargs):
    with get_cursor() as cur:
        for record in records:
            validated = PubMedRecord(**record)
            cur.execute("""
                INSERT INTO raw.pubmed (pmid, title, abstract, ...)
                VALUES (%s, %s, %s, ...)
                ON CONFLICT (pmid) DO UPDATE SET
                    title = EXCLUDED.title,
                    _loaded_at = NOW()
            """, (validated.pmid, validated.title, ...))
    return {'status': 'success', 'records_inserted': len(records)}
```

#### 4. Register

- Add to `fetchers/__init__.py`
- Add to `FETCHERS` dict in `fetch_data.py`
- Create CronJob manifest
- Add to `kustomization.yaml`
- Add seed SQL entries
- Add SOURCE_METADATA

#### 5. Test

```python
# tests/test_pubmed_fetcher.py
def test_fetcher_init():
    f = PubMedFetcher()
    assert f.SOURCE_NAME == "pubmed"

def test_get_latest_url():
    f = PubMedFetcher()
    assert "eutils" in f.get_latest_url()

def test_fetch_with_mock(requests_mock):
    requests_mock.get("https://eutils.ncbi.nlm.nih.gov/...", json={...})
    f = PubMedFetcher()
    result = f.fetch()
    assert result['status'] == 'success'
```

## Hybrid CI Fetch Strategy

- **Broad ingest** (PubMed, OpenAlex): Fetch all recent pharma-relevant content daily. No query scoping needed.
- **Query-scoped** (HTA, USPTO CI, Cochrane, Journal RSS, EPO, News, SEC EDGAR): Read search terms from `meta.ci_search_terms` table at fetch time. Terms are manageable via direct SQL or future Admin App.

### Seeding Search Terms

```sql
INSERT INTO meta.ci_search_terms (term_type, term_value) VALUES
('therapeutic_area', 'cardiovascular'),
('therapeutic_area', 'oncology'),
('drug_name', 'pembrolizumab'),
('drug_name', 'trastuzumab'),
('company', 'Pfizer'),
('company', 'Roche'),
('mesh_term', 'Transcatheter Aortic Valve Replacement')
ON CONFLICT (term_type, term_value) DO NOTHING;
```

## Verification Commands

```bash
# Check molecule source data after CronJob run
kubectl exec postgres-cluster-1 -n infra -- \
  psql -U postgres -d dk_data -c \
  "SELECT table_name, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'mol_raw' ORDER BY n_live_tup DESC;"

# Check CI source data
kubectl exec postgres-cluster-1 -n infra -- \
  psql -U postgres -d dk_data -c \
  "SELECT table_name, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'raw' ORDER BY table_name;"

# Check catalog health
kubectl exec postgres-cluster-1 -n infra -- \
  psql -U postgres -d dk_data -c \
  "SELECT source_name, is_active, staleness_threshold_hours FROM meta.data_sources ORDER BY source_name;"

# Check API views
curl https://data.preview.behaviorlabs.ai/pubmed_publications?limit=5
curl https://data.preview.behaviorlabs.ai/ema_regulatory_decisions?limit=5

# Trigger a specific CI source
kubectl create job test-pubmed-$(date +%s) \
  --from=cronjob/fetch-pubmed -n dk-data-prod
```

## Sprint Execution Order

1. **Sprint 1** (P1): Enable Tier 2A molecule sources — 5 sources, config-only
2. **Sprint 2** (P3): Implement PubMed, OpenAlex CI, EMA Regulatory — 3 full implementations
3. **Sprint 3** (P2): Enable Tier 3 molecule sources — 8 sources, config-only
4. **Sprint 4** (P4): Implement credential-gated sources (when creds obtained)
5. **Sprint 5** (P5): Implement Journal RSS, USPTO CI, HTA — 3 full implementations
6. **Sprint 6** (P6): Implement EPO, Cochrane, News, SEC EDGAR — 4 full implementations
7. **Sprint 7** (P7): Fix ACC TVC source
