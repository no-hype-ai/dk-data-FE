# TAVR Data Platform - API Examples

This document provides example queries for the PostgREST API endpoints.

## Base URL

```
Development: http://localhost:3030
Production: https://api.your-domain.com
```

## Authentication

Some endpoints require JWT authentication. Generate a token:

```python
import jwt
from datetime import datetime, timedelta

token = jwt.encode(
    {"role": "analyst", "exp": datetime.utcnow() + timedelta(hours=24)},
    "your-jwt-secret",
    algorithm="HS256"
)
```

Use in requests:
```bash
curl -H "Authorization: Bearer <token>" http://localhost:3030/catalog
```

---

## Data Catalog

### List All Data Sources (Public)

```bash
curl "http://localhost:3030/catalog_public"
```

### Full Catalog with Health Status (Authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/catalog"
```

### Filter by Topic Tags

```bash
# Sources tagged with 'cms'
curl "http://localhost:3030/catalog_public?topic_tags=cs.{cms}"

# Sources tagged with 'hospital' AND 'quality'
curl "http://localhost:3030/catalog_public?topic_tags=cs.{hospital,quality}"
```

### Filter by Health Status

```bash
# Only healthy sources
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/catalog?health_status=eq.healthy"

# Unhealthy or stale sources
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/catalog?health_status=neq.healthy"
```

### Select Specific Fields

```bash
curl "http://localhost:3030/catalog_public?select=source_name,health_status,freshness_hours"
```

---

## System Health

### Health Check

```bash
curl "http://localhost:3030/health"
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "database": "up",
    "postgrest": "up",
    "catalog": {
      "total_sources": 5,
      "healthy_count": 4,
      "stale_count": 1,
      "unhealthy_count": 0
    },
    "jobs": {
      "total_jobs": 7,
      "running_jobs": 0
    }
  }
}
```

---

## Batch Jobs

### List All Jobs (Authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/jobs"
```

### Filter Enabled Jobs Only

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/jobs?is_enabled=eq.true"
```

### Get Job with Associated Sources

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/jobs?select=job_name,description,cron_schedule,source_names"
```

### Job Run History

```bash
# Last 10 runs
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/job_runs?limit=10"

# Failed runs only
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/job_runs?status=eq.failure"

# Runs for a specific job
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/job_runs?job_name=eq.fetch-cms-all"
```

---

## Targets

### List All Targets (Public - Limited Fields)

```bash
curl "http://localhost:3030/targets_public"
```

### Full Target Details (Authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/targets"
```

### Filter by Tier

```bash
# Tier A targets only
curl "http://localhost:3030/targets_public?tier_classification=eq.A"

# Tier A or B
curl "http://localhost:3030/targets_public?tier_classification=in.(A,B)"
```

### Filter by State

```bash
curl "http://localhost:3030/targets_public?state=eq.CA"
```

### Sort by Score

```bash
# Highest scores first (full data)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/targets?order=total_trs.desc"
```

### Pagination

```bash
# First 20 results
curl "http://localhost:3030/targets_public?limit=20&offset=0"

# Next 20 results
curl "http://localhost:3030/targets_public?limit=20&offset=20"
```

### Combined Filters

```bash
# Top 10 Tier A targets in California, sorted by score
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/targets?tier_classification=eq.A&state=eq.CA&order=total_trs.desc&limit=10"
```

---

## Hospitals

### List All Hospitals

```bash
curl "http://localhost:3030/hospitals"
```

### Filter by TAVR Certification

```bash
curl "http://localhost:3030/hospitals?has_tavr_certification=eq.true"
```

### Filter by State and Type

```bash
curl "http://localhost:3030/hospitals?state=eq.TX&hospital_type=eq.Acute Care Hospitals"
```

### HPSA Designated Hospitals

```bash
curl "http://localhost:3030/hospitals?is_hpsa_primary_care=eq.true"
```

---

## Scoring Details

### Get Scoring Breakdown for a Hospital (Authenticated)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/scoring_details?hospital_id=eq.030064"
```

### Filter by Domain

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3030/scoring_details?domain=eq.clinical_readiness"
```

---

## Job Trigger API

The Job Trigger service runs on port 8000.

### List Available Jobs

```bash
curl "http://localhost:8000/jobs"
```

### Trigger a Job

```bash
curl -X POST "http://localhost:8000/jobs/fetch-cms-all/trigger"

# With user attribution
curl -X POST "http://localhost:8000/jobs/fetch-cms-all/trigger?user=jsmith"
```

### Check Job Status

```bash
curl "http://localhost:8000/runs/123"
```

### List Recent Runs

```bash
curl "http://localhost:8000/runs?limit=20"

# Filter by status
curl "http://localhost:8000/runs?status=running"
```

### Health Check

```bash
curl "http://localhost:8000/health"
```

---

## PostgREST Operators Reference

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `?state=eq.CA` |
| `neq` | Not equals | `?status=neq.healthy` |
| `gt` | Greater than | `?total_trs=gt.800` |
| `gte` | Greater than or equal | `?total_trs=gte.600` |
| `lt` | Less than | `?total_trs=lt.400` |
| `lte` | Less than or equal | `?total_trs=lte.200` |
| `like` | Pattern match (case-sensitive) | `?hospital_name=like.*Medical*` |
| `ilike` | Pattern match (case-insensitive) | `?hospital_name=ilike.*medical*` |
| `in` | In list | `?state=in.(CA,TX,FL)` |
| `is` | Is null/true/false | `?completed_at=is.null` |
| `cs` | Contains (arrays) | `?topic_tags=cs.{cms}` |
| `cd` | Contained by (arrays) | `?topic_tags=cd.{cms,hospital}` |
| `ov` | Overlaps (arrays) | `?topic_tags=ov.{cms,hrsa}` |

### Ordering

```bash
# Ascending (default)
?order=created_at.asc

# Descending
?order=total_trs.desc

# Multiple columns
?order=state.asc,total_trs.desc
```

### Pagination

```bash
?limit=50&offset=0    # First 50
?limit=50&offset=50   # Next 50
```

### Field Selection

```bash
?select=hospital_id,hospital_name,state,total_trs
```

---

## OpenAPI Specification

PostgREST automatically generates an OpenAPI specification:

```bash
curl "http://localhost:3030/"
```

This returns the full OpenAPI 3.0 spec documenting all available endpoints.
