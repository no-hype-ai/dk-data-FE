---
name: infra-check
description: "This skill should be used when the user asks to \"start services\", \"check infra\", \"docker up\", \"verify environment\", \"start dev\", \"check health\", \"is everything running\", or needs to manage local development infrastructure or verify staging connectivity."
version: 0.1.0
---

# Infrastructure Check

Manage local development infrastructure and verify environment health for PR validation.

## Environment Detection

Detect the active environment mode before any action:

```bash
# Docker Compose mode
docker compose ps --format json 2>/dev/null && echo "MODE=docker-compose"

# K3d mode
k3d cluster list 2>/dev/null | grep -q "behavior-labs" && echo "MODE=k3d"

# Staging VPN
kubectl --context k3s-master-1 get nodes 2>/dev/null && echo "STAGING=connected"
```

## Operations

### Start (`/infra-check start`)

1. Start infrastructure services:
   ```bash
   make docker-up
   ```
2. Wait for services to be healthy (poll `docker compose ps` for 30s max).
3. Run database migrations:
   ```bash
   make db-migrate
   ```
4. Start dev servers (instruct user to run in separate terminal):
   ```bash
   doppler run -- pnpm dev
   ```
5. Verify all endpoints respond (see Health Checks below).

### Stop (`/infra-check stop`)

```bash
make docker-down
```
Preserves data volumes. Use `make docker-destroy` only if explicitly requested.

### Status (`/infra-check status`)

Run all health checks and present the status table.

### Restart (`/infra-check restart`)

Stop then start. Preserve data volumes.

## Health Checks

Run these checks and present results as a table:

| Check | Command | Expected |
|-------|---------|----------|
| Docker services | `docker compose ps` | All running/healthy |
| PostgreSQL | `docker compose exec postgres pg_isready` | Accepting connections |
| Redis | `docker compose exec redis redis-cli ping` | PONG |
| API health | `curl -sf http://localhost:3002/health` | 200 OK |
| App responds | `curl -sf -o /dev/null -w "%{http_code}" http://localhost:3000` | 200 or 307 |
| Admin responds | `curl -sf -o /dev/null -w "%{http_code}" http://localhost:3001` | 200 or 307 |
| DB migrations | `cd packages/database && npx prisma migrate status` | Up to date |

### Staging Checks (VPN required)

If staging access needed:
1. Verify VPN: `kubectl --context k3s-master-1 get nodes`
2. If not connected, instruct user: "Run `/env.vpn connect` first"
3. Check pods: `kubectl --context k3s-master-1 get pods -n behaviorlabs`
4. Check deployments: `kubectl --context k3s-master-1 get deployments -n behaviorlabs`

## Output Format

Present results as:

```
## Infrastructure Status

**Mode**: Docker Compose | K3d | Staging
**Overall**: All healthy | Degraded | Down

| Service | Port | Status | Details |
|---------|------|--------|---------|
| ...     | ...  | ...    | ...     |
```

## Additional Resources

For the complete service port reference, see **`references/service-ports.md`**.
