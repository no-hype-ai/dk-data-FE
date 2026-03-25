# dk-data Alert Rules

The canonical alert rules file is `k8s/base/alert-rules.yaml`.

It lives inside the kustomize directory tree because kustomize does not allow
resource references outside its root. The file is included as a resource in
`k8s/base/kustomization.yaml` and applied to all overlays (dev, staging, prod).

All alerts carry `product: dk-data` and `service: dk-data` labels for routing
in the shared Mimir / Alertmanager infrastructure.
