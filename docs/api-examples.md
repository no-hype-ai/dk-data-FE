# API Examples

Last Updated: 2026-03-28

## Base URLs

| Environment | URL |
|-------------|-----|
| Production | `https://data.behaviorlabs.ai` |
| Staging | `https://data.staging.behaviorlabs.ai` |
| Local (PostgREST) | `http://localhost:3000` |
| Local (Job Trigger) | `http://localhost:8000` |

## Authentication

```python
import jwt
from datetime import datetime, timedelta

token = jwt.encode(
    {"role": "analyst", "exp": datetime.utcnow() + timedelta(hours=24)},
    "YOUR_JWT_SECRET",  # From Doppler: JWT_SECRET
    algorithm="HS256"
)
```

```bash
export TOKEN="<jwt-from-above>"
curl -H "Authorization: Bearer $TOKEN" https://data.behaviorlabs.ai/data_catalog
```

### Database Roles

| Role | Access |
|------|--------|
| `web_anon` | `api.health`, `api.data_catalog` only (no auth needed) |
| `analyst` | All `api.*` views, `mol_gold.*`, `mol_silver.*` (read-only) |
| `api_user` | All schemas (read-only) |

---

## Health & Catalog

```bash
# Health check (public)
curl https://data.behaviorlabs.ai/health

# Data source catalog with freshness (authenticated)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/data_catalog"

# Only active sources
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/data_catalog?is_active=eq.true"

# Stale sources (no refresh in >48h)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/data_catalog?health_status=neq.healthy"
```

---

## Molecule Profile (Gold)

```bash
# Molecule profile by ChEMBL ID
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecule_profile?chembl_id=eq.CHEMBL25"

# Top 10 molecules in Phase 3 clinical trials
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecule_profile?max_phase=eq.3&order=citation_count.desc&limit=10"

# Select specific fields
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecule_profile?select=chembl_id,canonical_name,max_phase,molecule_type,mechanism_of_action"
```

---

## Molecules (Silver)

```bash
# Find molecule by InChI Key
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecules?inchi_key=eq.XUJNEKJLAYQKCS-UHFFFAOYSA-N"

# Small molecules only, approved (max_phase=4)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecules?molecule_type=eq.small_molecule&max_phase=eq.4&limit=50"

# Molecules by molecule_type with Lipinski properties
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecules?molecule_type=eq.small_molecule&select=chembl_id,canonical_name,molecular_weight,alogp,hbd,hba,num_ro5_violations"
```

---

## Clinical Trials (Silver)

```bash
# Trials for a specific molecule (by molecule_id)
MOL_ID="<uuid-from-molecules-query>"
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/clinical_trials?molecule_id=eq.$MOL_ID"

# Active Phase 3 trials
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/clinical_trials?phase=eq.PHASE3&overall_status=eq.RECRUITING&order=enrollment.desc&limit=20"

# Trials with results
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/clinical_trials?has_results=eq.true&select=nct_id,title,phase,overall_status,completion_date"
```

---

## Adverse Events (Silver)

```bash
# Adverse events for a molecule, sorted by report count
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/adverse_events?molecule_id=eq.$MOL_ID&order=report_count.desc&limit=20"

# Most fatal adverse events (death_count > 10)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/adverse_events?death_count=gt.10&order=death_count.desc&limit=20"
```

---

## Binding Affinities (Silver)

```bash
# High-affinity binders (Ki < 10 nM) for a molecule
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/binding_affinities?molecule_id=eq.$MOL_ID&ki_nm=lt.10&order=ki_nm.asc"

# Filter by UniProt target
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/binding_affinities?uniprot_id=eq.P00533&order=activity_value_nm.asc&limit=50"
```

---

## Competitive Landscape (Gold)

```bash
# Competitive landscape for a therapeutic area
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/competitive_landscape?select=chembl_id,canonical_name,phase,company,indication"

# Company pipeline
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/company_pipeline?company=ilike.*pfizer*&order=max_phase.desc"
```

---

## Molecule Aliases / Identifier Lookup

```bash
# Find molecule by brand name (FAERS-style alias lookup)
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/molecule_aliases?alias_name_normalized=eq.keytruda&select=molecule_id,alias_name,alias_type"

# All identifiers for a molecule
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/identifier_mappings?molecule_id=eq.$MOL_ID&order=confidence.desc"
```

---

## Publications (Silver)

```bash
# Recent publications for a molecule
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/publications?molecule_id=eq.$MOL_ID&order=publication_date.desc&limit=20"

# High-citation publications
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/publications?cited_by_count=gt.100&order=cited_by_count.desc&limit=20"
```

---

## KOL Profiles (Gold)

```bash
# Top KOLs by publication count
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/kol_profiles?order=publication_count.desc&limit=20"

# KOLs associated with a molecule
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.behaviorlabs.ai/kol_drug_associations?molecule_id=eq.$MOL_ID&order=association_strength.desc"
```

---

## Job Trigger API

The Job Trigger service runs on port 8000.

```bash
# Health check
curl http://localhost:8000/health

# Data source freshness
curl http://localhost:8000/api/v1/monitoring/freshness

# Trigger a specific ingestion job (by CronJob name)
curl -X POST http://localhost:8000/api/v1/jobs/fetch-pubmed/trigger

# View recent job runs
curl http://localhost:8000/api/v1/monitoring/sources
```

---

## PostgREST Operators Reference

| Operator | Meaning | Example |
|----------|---------|---------|
| `eq` | Equals | `?max_phase=eq.4` |
| `neq` | Not equals | `?status=neq.inactive` |
| `gt`, `gte` | Greater than (or equal) | `?ki_nm=gt.10` |
| `lt`, `lte` | Less than (or equal) | `?ki_nm=lt.1` |
| `in` | In set | `?phase=in.(PHASE2,PHASE3)` |
| `like` | Case-sensitive pattern | `?canonical_name=like.*formin*` |
| `ilike` | Case-insensitive pattern | `?canonical_name=ilike.*formin*` |
| `is` | NULL check | `?inchi_key=is.null` |
| `cs` | Array contains | `?conditions=cs.{diabetes}` |
| `order` | Sort | `?order=report_count.desc` |
| `limit`, `offset` | Pagination | `?limit=50&offset=100` |
| `select` | Column projection | `?select=chembl_id,canonical_name` |

---

## Direct Database Queries (in-cluster)

```bash
# Via job-trigger pod
kubectl exec -n dk-data-prod deploy/job-trigger -- python3 -c "
import psycopg2, os
conn = psycopg2.connect(
    host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
    user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
    dbname=os.environ['POSTGRES_DB']
)
cur = conn.cursor()
cur.execute(\"SELECT source_name, last_successful_refresh, record_count FROM meta.data_sources ORDER BY last_successful_refresh DESC NULLS LAST\")
for r in cur.fetchall(): print(r)
conn.close()
"

# Check raw layer record counts
kubectl exec -n dk-data-prod deploy/job-trigger -- python3 -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ['POSTGRES_HOST'], port=os.environ['POSTGRES_PORT'],
    user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'],
    dbname=os.environ['POSTGRES_DB'])
cur = conn.cursor()
for table in ['pubmed', 'bindingdb', 'sider', 'clinicaltrials', 'openfda_faers']:
    cur.execute(f'SELECT COUNT(*) FROM mol_raw.{table}')
    print(f'mol_raw.{table}:', cur.fetchone()[0])
conn.close()
"
```
