# Contract: Required Keys in dk-data-applications/prd

All CronJob manifests source env vars from the `dk-data-secrets` Kubernetes secret, which is
populated by the Doppler operator from project `dk-data-applications`, config `prd`.

The following keys must exist in that project with real (non-placeholder) values:

## Credential Keys

| Key | Used By | Status |
|-----|---------|--------|
| `EPO_CONSUMER_KEY` | `fetch-epo` CronJob → `epo_ops.py` | ✅ Set (2026-03-31) |
| `EPO_CONSUMER_SECRET` | `fetch-epo` CronJob → `epo_ops.py` | ✅ Set (2026-03-31) |
| `EUIPO_API_KEY` | `fetch-euipo-trademarks`, `fetch-euipo-designs` | ✅ Set |
| `EUIPO_SECRET_KEY` | `fetch-euipo-trademarks`, `fetch-euipo-designs` | ✅ Set |
| `NCBI_API_KEY` | `fetch-pubmed` CronJob → `pubmed.py` | ✅ Set |
| `OPENALEX_API_KEY` | `fetch-openalex-ci` CronJob → `openalex_ci.py` | ✅ Set |
| `WHO_ICD_CLIENT_ID` | `fetch-who-icd` CronJob → `who_icd.py` | ✅ Set |
| `WHO_ICD_CLIENT_SECRET` | `fetch-who-icd` CronJob → `who_icd.py` | ✅ Set |
| `LITELLM_API_KEY` | Agent CronJobs | ✅ Set |
| `USPTO_API_KEY` | `fetch-uspto-patents`, `fetch-uspto-ci` | ⚠️ CHANGEME — issue #170 |
| `USPTO_TSDR_API_KEY` | `fetch-uspto-trademarks` | ⚠️ CHANGEME — issue #170 |
| `DRUGBANK_API_KEY` | `fetch-drugbank` | ⚠️ Empty (intentional) — XML seed covers bulk data |

## Infrastructure Keys

| Key | Used By | Status |
|-----|---------|--------|
| `POSTGRES_HOST` | All CronJobs | ✅ Set |
| `POSTGRES_PORT` | All CronJobs | ✅ Set |
| `POSTGRES_USER` | All CronJobs | ✅ Set |
| `POSTGRES_PASSWORD` | All CronJobs | ✅ Set |
| `POSTGRES_DB` | All CronJobs | ✅ Set |
| `DATABASE_URL` | Agent CronJobs, job-trigger | ✅ Set |
| `LITELLM_BASE_URL` | Agent CronJobs | ✅ Set |
| `JWT_SECRET` | job-trigger API auth | ✅ Set |
| `GHCR_DOCKERCONFIGJSON` | Image pull (ghcr-credentials secret) | ✅ Set |

## Staging Override

The staging overlay (`k8s/overlays/staging/kustomization.yaml`) patches the DopplerSecret
to use `config: stg` instead of `prd`. All keys above must also exist in `dk-data-applications/stg`.
