#!/usr/bin/env bash
# Launcher for dashboards/hydration-dashboard.html that:
#   1. Confirms the kubectl port-forward tunnels are up (PgBouncer 6432
#      and PostgREST 3001) — opens them if not.
#   2. Mints a short-lived (8h) JWT for the api_user role using
#      JWT_SECRET pulled from the dk-data-secrets k8s Secret.
#   3. Opens the dashboard in the default browser with both URL params.
#
# Usage:
#   ./dashboards/open-dashboard.sh           # against dk-data-prod
#   NS=dk-data-staging ./dashboards/open-dashboard.sh
#
# Requires: kubectl with KUBECONFIG set, the project venv at .venv/

set -euo pipefail

NS="${NS:-dk-data-prod}"
DASH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/hydration-dashboard.html"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/k3s-master-1.yaml}"

# 1. Tunnels
if ! lsof -ti:3001 >/dev/null 2>&1; then
  echo ">> opening postgrest tunnel on :3001"
  nohup kubectl -n "$NS" port-forward svc/postgrest 3001:3000 \
    > /tmp/postgrest-tunnel-${NS}.log 2>&1 &
  sleep 3
fi
if ! lsof -ti:6432 >/dev/null 2>&1; then
  echo ">> opening pgbouncer tunnel on :6432"
  nohup kubectl -n "$NS" port-forward svc/pgbouncer 6432:5432 \
    > /tmp/pgbouncer-tunnel-${NS}.log 2>&1 &
  sleep 3
fi

# 2. Mint JWT
SECRET=$(kubectl -n "$NS" get secret dk-data-secrets \
  -o jsonpath='{.data.JWT_SECRET}' | base64 -d)
TOKEN=$(JWT_SECRET="$SECRET" "$ROOT/.venv/bin/python" - <<'PY'
import os, time, jwt
print(jwt.encode(
    {"role": "api_user", "exp": int(time.time()) + 8*3600},
    os.environ["JWT_SECRET"], algorithm="HS256",
))
PY
)

# 3. Open
URL="file://${DASH}?postgrest=http://localhost:3001&token=${TOKEN}"
echo ">> opening: ${URL%%token=*}token=…"
open "$URL"
