# Quickstart — external-integration-foundation

## Anti-drift process (read first)

Feature 002 is a multi-week, cross-repo initiative. Without these process controls, the feature branch drifts from main and consuming-app repos move underfoot.

### Weekly rebase (drift audit D9)

Rebase `feature/002-external-integration-foundation` onto `main` **at least weekly**. Hot conflict zones:

- `src/dk_data/api/routes/data_platform.py` — US-15 router change
- `k8s/apps/postgrest/base/{configmap,deployment}.yaml` — US-2 edits
- `src/dk_data/observability/metrics.py` — Phase 6 cleanup
- `docker-compose.yml`, `src/dk_data/postgrest.conf` — US-9 sync
- `grafana/dashboards/*.json` — Phase 6 panel edits
- `k8s/apps/cronjobs/base/` — Phase 7 deletions

If a conflict takes more than 2 business days to resolve, escalate.

### Cross-repo coordination (drift audit D10)

Before Phase 5 starts, pin the following commits or coordinate cutover windows with owners:

| Repo | Files we will touch | Owner coordination needed |
|---|---|---|
| behavior-labs-ai | `apps/admin/lib/dk-data/postgrest-client.ts`, `apps/api/src/competitive-intel/sources/dk-data-fe.client.ts`, 4 research agents | Confirm admin-app + CI + research agent owners are ready |
| ground-truth-charlie | `src/lib/adapters/pubmed-adapter.ts`, `src/lib/adapters/openalex-adapter.ts`, evidence pipeline | Confirm evidence pipeline owner is ready |
| trials-predictor | `app/backend/sqlmesh_project/macros/identifier_utils.py` | Confirm owner is ready |

Write the coordination outcome to `docs/reports/phase-5-coordination.md` before starting Phase 5a.

### Mid-implementation `/dk.analyze` checkpoints (drift audit ON1)

Run `/dk.analyze` on this feature dir after each major phase completes:
- After Phase 3 (adapter v0.1 published)
- After Phase 4 (migrations 215–218 landed on staging)
- After Phase 5 (consumer migrations complete)
- **Gating**: Phase 4b production cutover (T089a) does not run until the last `/dk.analyze` is green.

---

## For dk-data-FE contributors

### Run the spec pipeline locally

```bash
# From dk-data-FE repo root
cd /Users/pschloz/Desktop/DataKinetic/dk-data-FE
git checkout feature/002-external-integration-foundation

# Verify environment
python -m venv venv && source venv/bin/activate
pip install -e .[dev]

# Bring up local postgres + PostgREST via docker
docker-compose up -d postgres pgbouncer postgrest metering-proxy

# Apply existing migrations (through 214)
psql -h localhost -p 5433 -U postgres -d dk_data \
  -f src/dk_data/sql/init_database.sql
ls src/dk_data/sql/migrations/ | sort | while read f; do
  psql -h localhost -p 5433 -U postgres -d dk_data \
    -f "src/dk_data/sql/migrations/$f"
done
```

### Migration number renumber-at-merge policy (drift audit D5)

Feature 002 reserves migrations 215–218 + 220. **Before merging**, run:

```bash
# Check the highest migration number on main
git fetch origin main
HIGHEST=$(git ls-tree -r origin/main --name-only src/dk_data/sql/migrations/ \
  | grep -oE '^src/dk_data/sql/migrations/[0-9]+' \
  | sed 's|.*/||' \
  | sort -n \
  | tail -1)

# If HIGHEST >= 215, renumber this feature's migrations upward
# Example: if main has 216, rename our 215→219, 216→220, 217→221, 218→222, 220→224
```

Renaming checklist:
1. `git mv` each migration file
2. Update `tasks.md` task descriptions
3. Update `contracts/migration-ddl.md` filenames
4. Update `plan.md` §9.11 migration numbering table
5. Update `memory/decisions.md` F-D010 sequence
6. Re-run tests

### Write the new migrations (US-2, US-4, US-5, US-6, US-20)

Use the DDL sketches in `contracts/migration-ddl.md` as your starting point. Each migration must:

1. Be idempotent (`IF NOT EXISTS`, `CREATE OR REPLACE`)
2. Be wrapped in a transaction (`BEGIN`/`COMMIT`) where possible
3. Grant to `analyst, api_user` only (NEVER `web_anon`)
4. Have a matching pytest case in `tests/migrations/test_<number>_<name>.py`

Sequence: 215 → 216 → 217 → 218 → 220. Do not run 216 before 215. Do not run 218 before provisioning API keys in the metering proxy (see US-3).

### Add the FastAPI JWT dependency (US-15)

```bash
# Create the auth dependency
cat > src/dk_data/api/dependencies/auth.py <<'PY'
from fastapi import Header, HTTPException, status
import jwt
import os

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
ALLOWED_ROLES = {"analyst", "api_user"}

async def verify_jwt(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization[len("Bearer "):]
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if claims.get("role") not in ALLOWED_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role not allowed: {claims.get('role')}")
    return claims
PY

# Apply at router level
# Edit src/dk_data/api/routes/data_platform.py:
#   from ..dependencies.auth import verify_jwt
#   router = APIRouter(
#       prefix="/data-platform",
#       tags=["data-platform"],
#       dependencies=[Depends(verify_jwt)],
#   )
```

### Run the test suite

```bash
# Unit + integration tests (real postgres, no mocks)
pytest tests/migrations/ -v
pytest tests/api/test_data_platform_auth.py -v
pytest tests/observability/test_metric_coverage.py -v
```

---

## For consuming-app developers migrating to the client

### Install

**TypeScript**:
```bash
npm install @datakinetic/dk-data-client
```

**Python**:
```bash
pip install dk-data-client
# or
uv add dk-data-client
```

### Configure

Required env vars (provisioned by dk-data operators per US-3):

```bash
export DK_DATA_METERING_PROXY_URL=https://data.behaviorlabs.ai
export DK_DATA_API_KEY=dk_data_<alias>_<suffix>
```

### First call

**TypeScript**:
```typescript
import { DkDataClient, DkDataNotFoundError } from "@datakinetic/dk-data-client";

const client = new DkDataClient({
  meteringProxyUrl: process.env.DK_DATA_METERING_PROXY_URL!,
  apiKey: process.env.DK_DATA_API_KEY!,
  fallbackMode: "upstream", // or "strict" or "hydrate"
});

try {
  const molecule = await client.molecules.resolve("durvalumab");
  const profile = await client.molecules.getProfile(molecule.id);
  console.log(profile.drug_type, profile.regulatory_status);
} catch (err) {
  if (err instanceof DkDataNotFoundError) {
    // handle "we don't know this molecule"
  } else {
    throw err;
  }
}
```

**Python**:
```python
from dk_data_client import DkDataClient, DkDataNotFoundError

client = DkDataClient(
    metering_proxy_url=os.environ["DK_DATA_METERING_PROXY_URL"],
    api_key=os.environ["DK_DATA_API_KEY"],
    fallback_mode="strict",
)

try:
    molecule = await client.molecules.resolve("durvalumab")
    profile = await client.molecules.get_profile(molecule.id)
except DkDataNotFoundError:
    ...
```

### Migrating existing hand-rolled code

1. Find every direct `fetch()` / `httpx.get()` / `psycopg2.connect()` to dk-data — replace with client calls
2. Find every hardcoded upstream-API call (PubChem, FDA, FAERS, CT.gov, EMA) — wrap in `client.molecules.get*()` with `fallbackMode: "upstream"` or `"hydrate"`
3. Update catch blocks to handle typed errors (`DkDataAuthError`, `DkDataNotFoundError`, `DkDataRateLimitError`, etc.)
4. Remove hardcoded localhost fallbacks (e.g., `http://localhost:3100`)
5. Run the integration test suite against staging dk-data before production cutover

---

## For dk-data operators rotating the JWT secret

See `docs/runbooks/rotate-jwt-secret.md`. Summary:

```bash
# 1. Generate new secret
NEW_SECRET=$(openssl rand -base64 32)

# 2. Update Doppler
doppler secrets set JWT_SECRET="$NEW_SECRET" --config dk-data-prod

# 3. Roll metering proxy first (it mints JWTs; must know the new secret)
kubectl -n dk-data-prod rollout restart deployment/dk-data-metering-proxy
kubectl -n dk-data-prod rollout status deployment/dk-data-metering-proxy

# 4. Roll PostgREST (it verifies JWTs; must know the new secret)
kubectl -n dk-data-prod rollout restart deployment/postgrest
kubectl -n dk-data-prod rollout status deployment/postgrest

# 5. Roll FastAPI (same — verifies JWTs via verify_jwt dep)
kubectl -n dk-data-prod rollout restart deployment/dk-data-api
kubectl -n dk-data-prod rollout status deployment/dk-data-api

# 6. Verify — consumers see at most one transient 401 retry
curl -H "Authorization: Bearer $TEST_API_KEY" https://data.behaviorlabs.ai/molecules | head
```

Rotation target cadence: every 90 days or immediately on any suspected leak.

---

## For dk-data operators executing the rollback

See `docs/runbooks/rollback-web-anon-drop.md`. Summary:

```bash
# 1. Apply the rollback migration
psql -h <prod-host> -p <port> -U postgres -d dk_data \
  -f src/dk_data/sql/migrations/218_drop_web_anon_rollback.sql

# 2. Revert PGRST_DB_ANON_ROLE in k8s configmap
kubectl -n dk-data-prod edit configmap postgrest-config
# Set PGRST_DB_ANON_ROLE back to "web_anon"

# 3. Roll PostgREST to pick up the change
kubectl -n dk-data-prod rollout restart deployment/postgrest

# 4. Verify
curl https://data.behaviorlabs.ai/health
# Expected: 200 OK
```

Target time: under 5 minutes end-to-end.
