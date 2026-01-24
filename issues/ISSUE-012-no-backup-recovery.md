# ISSUE-012: No Database Backup and Recovery Strategy

**Project**: dk-data-FE
**Category**: Operations
**Priority**: P0 - Critical
**Status**: Open
**Date**: 2026-01-15

---

## Problem Statement

The platform has no defined backup strategy for the PostgreSQL database. There's no automated backup schedule, no tested recovery procedure, and no offsite backup storage. Data loss from hardware failure, human error, or ransomware would be catastrophic.

---

## Current State

| Component | Status |
|-----------|--------|
| Automated backups | ❌ Not configured |
| Point-in-time recovery | ❌ Not enabled |
| Backup verification | ❌ Not implemented |
| Recovery runbook | ❌ Does not exist |
| Offsite replication | ❌ Not configured |
| Backup encryption | ❌ N/A |

---

## Evidence from Codebase

### docker-compose.yml - Volume Definition

```yaml
volumes:
  postgres-data:
    driver: local
```

**Issue**: Local Docker volume with no backup mechanism.

### spec.md - Assumptions

```markdown
## Assumptions
- CloudNativePG operator is available for production PostgreSQL if database is deployed to Kubernetes.
```

**Issue**: CloudNativePG mentioned but not configured in GitOps manifests.

### GitOps Structure

```yaml
# .gitops/base/kustomization.yaml
resources:
  - namespace.yaml
  - postgrest/deployment.yaml
  # No PostgreSQL deployment - assumed external
  # No backup CronJob defined
```

---

## Risk Assessment

### Data Loss Scenarios

| Scenario | Likelihood | Impact | Recovery Without Backup |
|----------|------------|--------|------------------------|
| Hardware failure | Low | Critical | Impossible |
| Human error (DROP TABLE) | Medium | Critical | Impossible |
| Ransomware attack | Low | Critical | Pay ransom or lose data |
| Corrupted migration | Medium | High | Manual reconstruction |
| Kubernetes node failure | Medium | High | Volume may be lost |

### Business Impact

- **Hospital scores**: Weeks to regenerate from source APIs
- **Historical scoring**: Lost forever
- **Job history**: Lost
- **Configuration**: Recreatable from code

---

## Recovery Time Analysis

| Data Type | Without Backup | With Backup |
|-----------|---------------|-------------|
| Raw data (CMS, HRSA, ACC) | 4-8 hours (re-fetch) | 30 minutes |
| Staging/Mart data | 2-4 hours (SQLMesh run) | 30 minutes |
| Scoring history | **LOST** | 30 minutes |
| Job execution history | **LOST** | 30 minutes |
| Meta configuration | 1 hour (manual) | 30 minutes |

**Without backup**: RPO = ∞ (some data unrecoverable)
**With backup**: RPO = 1 hour (or configurable)

---

## Recommended Solutions

### Option A: CloudNativePG (Recommended for K8s)

#### A.1 PostgreSQL Cluster Definition

```yaml
# .gitops/base/database/cluster.yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: tavr-postgres
  namespace: tavr-data
spec:
  instances: 3  # Primary + 2 replicas

  storage:
    size: 50Gi
    storageClass: standard

  postgresql:
    parameters:
      max_connections: "200"
      shared_buffers: "256MB"

  backup:
    barmanObjectStore:
      destinationPath: "s3://tavr-backups/postgres"
      s3Credentials:
        accessKeyId:
          name: s3-creds
          key: ACCESS_KEY_ID
        secretAccessKey:
          name: s3-creds
          key: SECRET_ACCESS_KEY
      wal:
        compression: gzip
      data:
        compression: gzip
    retentionPolicy: "30d"

  # Scheduled backups
  scheduledBackups:
    - name: daily-backup
      schedule: "0 2 * * *"  # 2 AM daily
      backupOwnerReference: self
```

#### A.2 Backup Schedule

```yaml
# .gitops/base/database/scheduled-backup.yaml
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: tavr-daily-backup
spec:
  schedule: "0 2 * * *"
  backupOwnerReference: self
  cluster:
    name: tavr-postgres
```

### Option B: pg_dump CronJob (Simpler)

#### B.1 Backup CronJob

```yaml
# .gitops/base/database/backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: tavr-data
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  set -e

                  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
                  BACKUP_FILE="/backups/tavr_${TIMESTAMP}.sql.gz"

                  echo "Starting backup at $(date)"

                  pg_dump -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB \
                    --format=custom \
                    --compress=9 \
                    --verbose \
                    > $BACKUP_FILE

                  echo "Backup completed: $(ls -lh $BACKUP_FILE)"

                  # Upload to S3
                  aws s3 cp $BACKUP_FILE s3://tavr-backups/postgres/

                  # Clean up local file
                  rm $BACKUP_FILE

                  # Delete backups older than 30 days from S3
                  aws s3 ls s3://tavr-backups/postgres/ | \
                    awk '{print $4}' | \
                    while read file; do
                      DATE=$(echo $file | grep -oP '\d{8}')
                      if [ $(( ($(date +%s) - $(date -d "$DATE" +%s)) / 86400 )) -gt 30 ]; then
                        aws s3 rm s3://tavr-backups/postgres/$file
                      fi
                    done

                  echo "Backup and cleanup completed successfully"
              env:
                - name: POSTGRES_HOST
                  value: postgres
                - name: POSTGRES_USER
                  valueFrom:
                    secretKeyRef:
                      name: postgres-secrets
                      key: username
                - name: POSTGRES_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: postgres-secrets
                      key: password
                - name: POSTGRES_DB
                  value: edwards_tavr
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: postgres-secrets
                      key: password
                - name: AWS_ACCESS_KEY_ID
                  valueFrom:
                    secretKeyRef:
                      name: s3-creds
                      key: access-key
                - name: AWS_SECRET_ACCESS_KEY
                  valueFrom:
                    secretKeyRef:
                      name: s3-creds
                      key: secret-key
              volumeMounts:
                - name: backup-volume
                  mountPath: /backups
              resources:
                requests:
                  cpu: "100m"
                  memory: "256Mi"
                limits:
                  cpu: "1000m"
                  memory: "2Gi"
          volumes:
            - name: backup-volume
              emptyDir:
                sizeLimit: 10Gi
          restartPolicy: OnFailure
```

### Option C: Docker Compose (Local Dev)

#### C.1 Backup Script

```bash
#!/bin/bash
# scripts/backup_database.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups"
BACKUP_FILE="${BACKUP_DIR}/tavr_${TIMESTAMP}.sql.gz"

mkdir -p $BACKUP_DIR

echo "Starting backup..."

docker compose exec -T postgres pg_dump \
  -U postgres \
  -d edwards_tavr \
  --format=custom \
  --compress=9 \
  > $BACKUP_FILE

echo "Backup completed: $(ls -lh $BACKUP_FILE)"

# Keep only last 7 backups
ls -t ${BACKUP_DIR}/tavr_*.sql.gz | tail -n +8 | xargs -r rm
```

#### C.2 Restore Script

```bash
#!/bin/bash
# scripts/restore_database.sh

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 <backup_file>"
  echo "Available backups:"
  ls -la ./backups/*.sql.gz
  exit 1
fi

echo "WARNING: This will overwrite the current database!"
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

echo "Restoring from $BACKUP_FILE..."

docker compose exec -T postgres pg_restore \
  -U postgres \
  -d edwards_tavr \
  --clean \
  --if-exists \
  --verbose \
  < $BACKUP_FILE

echo "Restore completed."
```

---

## Recovery Procedures

### Scenario 1: Full Database Restore

```bash
# 1. List available backups
aws s3 ls s3://tavr-backups/postgres/

# 2. Download latest backup
aws s3 cp s3://tavr-backups/postgres/tavr_20260115_020000.sql.gz ./

# 3. Stop application (prevent writes during restore)
kubectl scale deployment postgrest --replicas=0 -n tavr-data
kubectl scale deployment job-trigger --replicas=0 -n tavr-data

# 4. Restore database
gunzip -c tavr_20260115_020000.sql.gz | \
  kubectl exec -i postgres-0 -n tavr-data -- \
  pg_restore -U postgres -d edwards_tavr --clean --if-exists

# 5. Restart applications
kubectl scale deployment postgrest --replicas=1 -n tavr-data
kubectl scale deployment job-trigger --replicas=1 -n tavr-data

# 6. Verify data
curl http://localhost:3030/targets?limit=1 | jq
```

### Scenario 2: Point-in-Time Recovery (CloudNativePG)

```yaml
# Create recovery cluster
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: tavr-postgres-recovery
spec:
  instances: 1

  bootstrap:
    recovery:
      source: tavr-postgres
      recoveryTarget:
        targetTime: "2026-01-15T10:00:00Z"  # Recover to this point

  externalClusters:
    - name: tavr-postgres
      barmanObjectStore:
        destinationPath: "s3://tavr-backups/postgres"
        s3Credentials:
          accessKeyId:
            name: s3-creds
            key: ACCESS_KEY_ID
          secretAccessKey:
            name: s3-creds
            key: SECRET_ACCESS_KEY
```

---

## Backup Verification

### Automated Restore Test

```yaml
# .gitops/base/database/backup-verify-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup-verify
spec:
  schedule: "0 4 * * 0"  # Weekly on Sunday
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: verify
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  # Get latest backup
                  LATEST=$(aws s3 ls s3://tavr-backups/postgres/ | sort | tail -1 | awk '{print $4}')
                  aws s3 cp s3://tavr-backups/postgres/$LATEST /tmp/backup.sql.gz

                  # Create temporary database
                  createdb -h $POSTGRES_HOST -U $POSTGRES_USER tavr_verify_$$

                  # Restore backup
                  gunzip -c /tmp/backup.sql.gz | \
                    pg_restore -h $POSTGRES_HOST -U $POSTGRES_USER -d tavr_verify_$$ --no-owner

                  # Verify table counts
                  psql -h $POSTGRES_HOST -U $POSTGRES_USER -d tavr_verify_$$ -c "
                    SELECT 'raw.cms_hospital_info' as tbl, COUNT(*) as cnt FROM raw.cms_hospital_info
                    UNION ALL
                    SELECT 'scoring.target_scores', COUNT(*) FROM scoring.target_scores
                  "

                  # Clean up
                  dropdb -h $POSTGRES_HOST -U $POSTGRES_USER tavr_verify_$$

                  echo "Backup verification completed successfully"
```

---

## Implementation Checklist

- [ ] Choose backup strategy (CloudNativePG vs pg_dump)
- [ ] Create S3 bucket for backups
- [ ] Configure IAM credentials for S3 access
- [ ] Deploy backup CronJob
- [ ] Test manual restore procedure
- [ ] Deploy backup verification job
- [ ] Document recovery runbook
- [ ] Set up alerting for backup failures
- [ ] Configure backup retention policy
- [ ] Train team on recovery procedures

---

## Backup Metrics to Monitor

| Metric | Alert Threshold |
|--------|-----------------|
| Last successful backup age | > 24 hours |
| Backup size trend | > 50% change |
| Backup duration | > 1 hour |
| S3 upload success | Any failure |
| Verification test result | Any failure |

---

## References

- [CloudNativePG: Backup and Recovery](https://cloudnative-pg.io/documentation/current/backup/)
- [PostgreSQL: pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html)
- [AWS S3: Lifecycle Policies](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)
- [Kubernetes: CronJob Best Practices](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
