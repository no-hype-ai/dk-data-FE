# Doppler Secret Configuration Reference

**Feature**: 012-platform-hardening (US5)
**Last Updated**: 2026-02-14

## Overview

All secrets for the dk-data platform are managed via Doppler. This document lists every required and optional secret, its purpose, format, and which services depend on it.

## Required Secrets

### Database Connection

| Secret Name | Purpose | Format | Required By |
|------------|---------|--------|-------------|
| `POSTGRES_HOST` | PostgreSQL server hostname | Hostname or IP | All CronJobs, PostgREST, Job Trigger |
| `POSTGRES_PORT` | PostgreSQL server port | Integer (default: 5432) | All CronJobs, PostgREST, Job Trigger |
| `POSTGRES_USER` | PostgreSQL username | String | All CronJobs, PostgREST, Job Trigger |
| `POSTGRES_PASSWORD` | PostgreSQL password | String (min 16 chars recommended) | All CronJobs, PostgREST, Job Trigger |
| `POSTGRES_DB` | PostgreSQL database name | String (default: dk_data) | All CronJobs, PostgREST, Job Trigger |

### Authentication

| Secret Name | Purpose | Format | Required By |
|------------|---------|--------|-------------|
| `JWT_SECRET` | PostgREST JWT signing secret | String (min 256-bit / 32 chars) | PostgREST |

## Credential-Gated API Keys

These secrets are required only for specific data sources. The CronJob will fail gracefully (log error, exit non-zero) if the key is missing.

| Secret Name | Purpose | Format | Required By | How to Obtain |
|------------|---------|--------|-------------|---------------|
| `NCBI_API_KEY` | NCBI E-utilities API key (raises limit from 3/s to 10/s) | String | fetch-pubmed CronJob | https://www.ncbi.nlm.nih.gov/account/settings/ |
| `OPENALEX_API_KEY` | OpenAlex API key (required since Feb 2026) | String | fetch-openalex-ci CronJob | https://openalex.org/settings/api |
| `DRUGBANK_API_KEY` | DrugBank API access key | String | fetch-drugbank CronJob | https://go.drugbank.com/public_users/sign_up |
| `EPO_CONSUMER_KEY` | EPO Open Patent Services OAuth2 client key | String | fetch-epo CronJob | https://developers.epo.org/ |
| `EPO_CONSUMER_SECRET` | EPO Open Patent Services OAuth2 client secret | String | fetch-epo CronJob | https://developers.epo.org/ |
| `PATENTSVIEW_API_KEY` | USPTO PatentsView API key | String | fetch-uspto-patents CronJob | https://patentsview.org/apis/keyrequest |
| `SEC_EDGAR_USER_AGENT` | SEC EDGAR required User-Agent header (format: `Name email@domain`) | String | fetch-sec-edgar CronJob | Use company email per SEC policy |
| `WHO_ICD_CLIENT_ID` | WHO ICD-11 API OAuth2 client ID | String | fetch-who-icd CronJob | https://icd.who.int/icdapi (optional — falls back to ICD-10 public API) |
| `WHO_ICD_CLIENT_SECRET` | WHO ICD-11 API OAuth2 client secret | String | fetch-who-icd CronJob | https://icd.who.int/icdapi |
| `PHARMGKB_API_KEY` | PharmGKB API key | String | fetch-pharmgkb CronJob | https://www.pharmgkb.org/page/apiAccess |

## Optional Secrets

| Secret Name | Purpose | Format | Required By |
|------------|---------|--------|-------------|
| `ANTHROPIC_API_KEY` | Claude SDK for AI enrichment/scoring | String (sk-ant-...) | Enrichment scripts |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint | URL | All services (observability) |

## Environment Setup

### New Environment Checklist

1. Create a new Doppler project or environment
2. Set all **Required Secrets** (database + JWT)
3. Set credential-gated keys for data sources you want to enable
4. Optional secrets can be added later

### Validation

Run the startup validation check to verify all critical secrets:

```bash
# In container
python -c "from dk_data.ingestion.utils.secret_check import validate_secrets; validate_secrets()"

# Or via Docker
docker run --env-file .env dk-data-test python -c "from dk_data.ingestion.utils.secret_check import validate_secrets; validate_secrets()"
```

## Secret Rotation

- Database passwords: Rotate quarterly
- API keys: Rotate annually or on team member departure
- JWT secret: Rotate if compromised; requires PostgREST restart
