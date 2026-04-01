# Manual Upload Sources — Operator Runbook

Four data sources require manual file download and upload rather than automated API fetching.
These sources have no CronJob; an operator must run the ingestion CLI after downloading the
latest file from the upstream publisher.

---

## acc_tvc — ACC Transcatheter Valve Certifications

**Publisher:** American College of Cardiology (ACC) / NCDR Public Reporting
**URL:** https://cvquality.acc.org/NCDR-Home/registries/outpatient-registries/tvt-registry
**Frequency:** Quarterly (or when ACC publishes updated certification list)
**Target table:** `hcs_raw.acc_tvc_certification`

### Download

1. Log in to the ACC NCDR Public Reporting portal.
2. Download the TVTMetrics / Hospitals merged CSV.
   - NCDR format columns: `FacilityBrandedName`, `State`, `TranscatheterValveCertification`, …
   - Legacy format columns: `Facility Name`, `Certification Type`, `Certification Date`, …
   - Both formats are supported; the loader auto-detects by column header.

### Upload

```bash
python -m dk_data.ingestion.main acc_tvc \
  --file /path/to/tvc_certifications.csv
```

---

## cms_inpatient — CMS Medicare Inpatient (TAVR DRG 266/267)

**Publisher:** CMS Provider Summary by Type of Service
**URL:** https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals
**Frequency:** Annually (CMS releases prior fiscal year data ~12–18 months after year-end)
**Target table:** `hcs_raw.cms_medicare_inpatient`

### Download

1. Go to the CMS data page above.
2. Select the desired fiscal year (e.g., 2023).
3. Download the full CSV file (`Medicare_Inpatient_Hospitals_by_Provider_and_Service_*.csv`).

### Upload

```bash
python -m dk_data.ingestion.main cms_inpatient \
  --file /path/to/Medicare_Inpatient_Hospitals_2023.csv \
  --fiscal-year 2023
```

**Note:** `--fiscal-year` is required. The loader filters to DRG codes 266 and 267 (TAVR
procedures) before inserting. All other DRG rows are discarded at load time.

---

## cms_hospital_info — CMS Hospital General Information

**Publisher:** CMS Provider Data Catalog
**URL:** https://data.cms.gov/provider-data/dataset/xubh-q36u
**Frequency:** Quarterly (CMS refreshes this dataset ~4× per year)
**Target table:** `hcs_raw.cms_hospital_general_info`

### Download

1. Go to the URL above.
2. Click **Download** → **CSV**.
   - Filename: `Hospital_General_Information.csv`

### Upload

```bash
python -m dk_data.ingestion.main cms_hospital_info \
  --file /path/to/Hospital_General_Information.csv
```

---

## cms_cost_reports — CMS Hospital Cost Reports (HCRIS)

**Publisher:** CMS Provider Compliance / HCRIS
**URL:** https://data.cms.gov/provider-compliance/cost-report
**Frequency:** Annually (prior fiscal year data released with ~18-month lag)
**Target table:** `hcs_raw.cms_cost_reports`

### Download

1. Go to the URL above.
2. Select the **Hospital Cost Report** dataset.
3. Download the full CSV (large file — typically 300–600 MB).
   - Filename pattern: `Hospital_Cost_Report_FY*.csv`

### Upload

```bash
python -m dk_data.ingestion.main cms_cost_reports \
  --file /path/to/Hospital_Cost_Report_FY2023.csv
```

---

## Checking ingestion status

After upload, verify the row count and last refresh time:

```sql
SELECT source_name, last_successful_refresh, last_record_count, last_status
FROM meta.data_sources
WHERE source_name IN ('acc_tvc', 'cms_inpatient', 'cms_hospital_info', 'cms_cost_reports')
ORDER BY source_name;
```

## Sources that do NOT require manual upload

The following sources were flagged in audit as potentially needing manual handling but are
fully automated via API fetchers and Kubernetes CronJobs — no operator action required:

| Source | CronJob | Notes |
|--------|---------|-------|
| `cms_usp` | `cronjob-fetch-cms-usp` | USP drug classification via CMSUSPFetcher |
| `cms_stabilis` | `cronjob-fetch-cms-stabilis` | Drug stability reference via CMSStabilisFetcher |
| `cms_dual_eligible` | `cronjob-fetch-cms-dual-eligible` | Dual eligible beneficiary data via CMSDualEligibleFetcher |

---

## Notes

- All 4 manual-upload sources write to `hcs_raw.*` tables, which feed `hcs_bronze.*` via SQLMesh.
- After uploading new data, run a SQLMesh plan to propagate changes through bronze → silver → gold:
  ```bash
  sqlmesh plan --select hcs_bronze.cms_hospital_general_info+ --auto-apply
  ```
- These sources have no `default_days_back` — the loader always processes the full file provided.
  Re-uploading the same file is idempotent (duplicate rows are rejected via `ON CONFLICT DO NOTHING`).
