# dk-data Bootstrap — Already Provisioned in dk-alchemy

The dk-data bootstrap resources are already provisioned in the dk-alchemy repository. No additional changes are needed there.

## Provisioned Resources

### ArgoCD AppProject
- **File:** `.gitops/repositories/dk-data-bootstrap-project.yaml`

### ArgoCD Applications
- **File:** `.gitops/external/dk-data-fe.yaml`

### Namespaces
- `dk-data-prod`
- `dk-data-staging`

### Doppler
- Secret: `dk-data-token` with PRD/STG tokens

### Grafana
- Contact points, notification policies, and alert rules defined in `grafana/alerts/dk-data.yaml`
