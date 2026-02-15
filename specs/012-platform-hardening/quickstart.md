# Quickstart: Platform Hardening Verification

## Prerequisites

- Docker installed locally
- kubectl access to staging cluster
- Doppler CLI configured

## US1: Verify Container Image Fix

### Build and test locally
```bash
# Build the image
docker build -t dk-data-test .

# Verify dk_data is importable
docker run --rm dk-data-test python -c "import dk_data; print('OK:', dk_data.__file__)"

# Verify CronJob entry points work
docker run --rm dk-data-test python -m dk_data.ingestion.fetch_data --help
docker run --rm dk-data-test python -m dk_data.ingestion.fetch_molecules --help
docker run --rm dk-data-test python -m dk_data.scripts.catalog_refresh --help
```

### Verify in cluster
```bash
# Trigger a test CronJob
kubectl create job test-fetch --from=cronjob/fetch-pubmed -n dk-data-staging

# Check logs (should NOT show ModuleNotFoundError)
kubectl logs -f job/test-fetch -n dk-data-staging

# Clean up
kubectl delete job test-fetch -n dk-data-staging
```

## US2: Verify API Views

### Query new views via PostgREST
```bash
# Set up auth token
export TOKEN=$(python3 -c "
import jwt, time
print(jwt.encode({'role':'api_user','exp':int(time.time())+3600}, 'your-jwt-secret', algorithm='HS256'))
")

# Test each new view (should return empty array or data, NOT an error)
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/company_pipeline
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/molecule_targets
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/trial_publication_features
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/sider_side_effects
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/bioactivity
curl -H "Authorization: Bearer $TOKEN" https://data.preview.behaviorlabs.ai/patents

# Verify unauthenticated access is rejected
curl -s -o /dev/null -w "%{http_code}" https://data.preview.behaviorlabs.ai/company_pipeline
# Should return 401
```

## US3: Verify Data Sources

### Trigger individual fetchers
```bash
# UniProt
kubectl create job test-uniprot --from=cronjob/fetch-uniprot -n dk-data-staging
kubectl logs -f job/test-uniprot -n dk-data-staging

# PDB
kubectl create job test-pdb --from=cronjob/fetch-pdb -n dk-data-staging
kubectl logs -f job/test-pdb -n dk-data-staging

# ORCID
kubectl create job test-orcid --from=cronjob/fetch-orcid -n dk-data-staging
kubectl logs -f job/test-orcid -n dk-data-staging
```

### Verify catalog entries
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://data.preview.behaviorlabs.ai/data_sources?source_name=in.(uniprot,pdb,orcid)"
# Should return 3 source entries with is_active=true
```

## US4: Verify Dependency Lock File

```bash
# Install from lock file
uv sync

# Verify reproducibility
uv pip freeze > /tmp/freeze1.txt
rm -rf .venv && uv sync
uv pip freeze > /tmp/freeze2.txt
diff /tmp/freeze1.txt /tmp/freeze2.txt
# Should show no differences

# Run tests
pytest tests/ -q
```

## US5: Verify Secret Documentation

```bash
# Check all secrets are documented
grep -c "^|" docs/DOPPLER_SECRETS.md  # Count documented secrets

# Verify startup validation
docker run --rm dk-data-test python -c "from dk_data.ingestion.utils.secret_check import validate_secrets; validate_secrets()"
# Should log warnings for missing secrets
```

## Full Validation

```bash
# Kustomize validation
kubectl kustomize k8s/overlays/staging --enable-helm > /dev/null && echo "Staging OK"
kubectl kustomize k8s/overlays/prod --enable-helm > /dev/null && echo "Prod OK"

# Full test suite
pytest tests/ -q

# Import check for all new fetchers
python -c "
from dk_data.ingestion.fetchers import UniProtFetcher, PDBFetcher, ORCIDFetcher
print('All new fetchers import successfully')
"
```
