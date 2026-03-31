# Data Model: Post-Deployment Fixes & Credential Audit

**Branch**: `021-post-deploy-fixes`

No schema changes in this feature. All fixes are configuration, credential, and fetcher-code changes only.

## Impacted Tables (Read-only Reference)

| Table | Schema | Change |
|-------|--------|--------|
| `hcs_raw.cms_ddinter` | hcs_raw | No change — existing data preserved; fetcher removed |
| `hcs_bronze.cms_ddinter` | hcs_bronze | No change — model retained with retirement comment |
| `mol_bronze.drugbank_data` | mol_bronze | No change — confirmed as DDI replacement source |
| `meta.data_sources` | meta | No new rows — DDInter entry removed by existing cleanup |
| `meta.refresh_log` | meta | DDInter entries stop accumulating after CronJob pruned |

## Kubernetes Secret: `dk-data-secrets`

Populated by DopplerSecret from `dk-data-applications/prd`. Keys updated in this feature:

| Key | Before | After |
|-----|--------|-------|
| `EPO_CONSUMER_KEY` | `CHANGEME_obtain_from_developers_epo_org` | Real OAuth2 consumer key |
| `EPO_CONSUMER_SECRET` | `CHANGEME_obtain_from_developers_epo_org` | Real OAuth2 consumer secret |
