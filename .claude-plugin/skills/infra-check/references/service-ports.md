# Service Port Reference

## Infrastructure Services (Docker Compose)

| Service | Container | Port | Protocol | Notes |
|---------|-----------|------|----------|-------|
| PostgreSQL | behavior-labs-postgres | 5432 | TCP | pgvector:pg16, user: postgres |
| Redis | behavior-labs-redis | 6379 | TCP | redis:7-alpine |
| MinIO | behavior-labs-minio | 9000 | HTTP | S3 API endpoint |
| MinIO Console | behavior-labs-minio | 9001 | HTTP | Web UI (admin/admin) |
| OpenSearch | behavior-labs-opensearch | 9200 | HTTP | REST API |
| OpenSearch Perf | behavior-labs-opensearch | 9600 | HTTP | Performance analyzer |

## Application Services (Local Dev)

| Service | Port | Framework | Start Command |
|---------|------|-----------|---------------|
| App (main frontend) | 3000 | Next.js 16 | `pnpm dev --filter=app` |
| Admin dashboard | 3001 | Next.js 16 | `pnpm dev --filter=admin` |
| API server | 3002 | NestJS 11 | `pnpm dev --filter=api` |

## Monitoring (Optional Profile)

| Service | Port | Notes |
|---------|------|-------|
| Grafana | 3003 | Default: admin/admin |
| Prometheus | 9090 | Metrics collection |
| OTel Collector | 4318 | HTTP OTLP endpoint |

## Knowledge Runtime Services

| Service | Port | Notes |
|---------|------|-------|
| LightRAG | 8020 | Knowledge extraction |
| Doc Processing | 8030 | Document parsing |

## Staging / Production (VPN Required)

Access via `kubectl --context k3s-master-1`:
- Namespace: `behaviorlabs`
- Services mirror local ports inside k8s
- Ingress handles external routing
