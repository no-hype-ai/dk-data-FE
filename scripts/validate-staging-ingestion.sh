#!/usr/bin/env bash
# validate-staging-ingestion.sh
# Staging validation script for the unified ingestion pipeline (main.py).
# Run after merging to staging and ArgoCD sync completes.
#
# Usage:
#   ./scripts/validate-staging-ingestion.sh              # Run all phases
#   ./scripts/validate-staging-ingestion.sh phase1        # Pre-flight only
#   ./scripts/validate-staging-ingestion.sh phase2        # Manual single-source runs
#   ./scripts/validate-staging-ingestion.sh phase3        # Incremental validation
#   ./scripts/validate-staging-ingestion.sh status        # Check CronJob status
set -euo pipefail

NS="${NAMESPACE:-dk-data-staging}"
PHASE="${1:-all}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAILURES=$((FAILURES + 1)); }
warn() { echo -e "  ${YELLOW}WARN${NC} $1"; }
FAILURES=0

# Find a running pod to exec into
get_pod() {
  kubectl -n "$NS" get pods -l app=job-trigger -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# Run SQL via psql in the job-trigger pod
run_sql() {
  local pod
  pod=$(get_pod)
  kubectl -n "$NS" exec "$pod" -- python3 -c "
import psycopg2, os, json
conn = psycopg2.connect(
    host=os.environ['POSTGRES_HOST'],
    port=os.environ.get('POSTGRES_PORT', '5432'),
    dbname=os.environ['POSTGRES_DB'],
    user=os.environ['POSTGRES_USER'],
    password=os.environ['POSTGRES_PASSWORD'],
)
cur = conn.cursor()
cur.execute(\"\"\"$1\"\"\")
rows = cur.fetchall()
for r in rows:
    print('\t'.join(str(c) for c in r))
conn.close()
" 2>/dev/null
}

# ──────────────────────────────────────────────────
# Phase 1: Pre-flight checks
# ──────────────────────────────────────────────────
phase1() {
  echo ""
  echo "═══════════════════════════════════════════════════"
  echo " Phase 1: Pre-flight Checks"
  echo "═══════════════════════════════════════════════════"

  # 1a. Check pod is running
  echo ""
  echo "1a. Job-trigger pod running"
  local pod
  pod=$(get_pod) && pass "Pod: $pod" || fail "No job-trigger pod found"

  # 1b. Verify main.py SOURCES count inside the container
  echo ""
  echo "1b. SOURCES dict has 22 entries"
  local count
  count=$(kubectl -n "$NS" exec "$(get_pod)" -- \
    python3 -c "from dk_data.ingestion.main import SOURCES; print(len(SOURCES))" 2>/dev/null)
  if [ "$count" = "22" ]; then
    pass "SOURCES count = $count"
  else
    fail "SOURCES count = ${count:-ERROR} (expected 22)"
  fi

  # 1c. Verify main.py has _meta_name resolver
  echo ""
  echo "1c. _meta_name resolver works"
  local meta_check
  meta_check=$(kubectl -n "$NS" exec "$(get_pod)" -- \
    python3 -c "from dk_data.ingestion.main import _meta_name; print(_meta_name('cms_inpatient'), _meta_name('pubmed'))" 2>/dev/null)
  if echo "$meta_check" | grep -q "cms_medicare_inpatient pubmed"; then
    pass "meta_name: $meta_check"
  else
    fail "meta_name: ${meta_check:-ERROR}"
  fi

  # 1d. Check meta.data_sources has all 22 sources
  echo ""
  echo "1d. meta.data_sources populated"
  local src_count
  src_count=$(run_sql "SELECT count(*) FROM meta.data_sources WHERE is_active = true")
  src_count=$(echo "$src_count" | tr -d '[:space:]')
  if [ "$src_count" -ge 22 ] 2>/dev/null; then
    pass "Active sources in meta: $src_count"
  else
    fail "Active sources in meta: ${src_count:-ERROR} (expected >= 22)"
  fi

  # 1e. Verify key source_name values exist
  echo ""
  echo "1e. Key source_name values match"
  local EXPECTED_NAMES=(
    pubmed ema_regulatory openalex_ci drugbank
    uspto_patents journal_rss uspto_ci hta_bodies
    epo_ops cochrane medical_news sec_edgar
    uniprot pdb orcid
    uspto_trademarks euipo_trademarks
    cms_medicare_inpatient cms_hospital_info
    cms_cost_reports acc_tvc hrsa_shortage_areas
  )
  for name in "${EXPECTED_NAMES[@]}"; do
    local found
    found=$(run_sql "SELECT source_name FROM meta.data_sources WHERE source_name = '$name'")
    found=$(echo "$found" | tr -d '[:space:]')
    if [ "$found" = "$name" ]; then
      pass "  $name"
    else
      fail "  $name NOT FOUND in meta.data_sources"
    fi
  done

  # 1f. CronJobs are deployed and active
  echo ""
  echo "1f. Ingestion CronJobs deployed"
  local total_ingestion
  total_ingestion=$(kubectl -n "$NS" get cronjobs -l app.kubernetes.io/component=ingestion --no-headers 2>/dev/null | wc -l | tr -d ' ')
  if [ "$total_ingestion" -ge 17 ] 2>/dev/null; then
    pass "Ingestion CronJobs deployed: $total_ingestion"
  else
    fail "Ingestion CronJobs: ${total_ingestion:-0} (expected >= 17)"
  fi

  echo ""
  echo "Phase 1 complete. Failures: $FAILURES"
}

# ──────────────────────────────────────────────────
# Phase 2: Single-source manual runs
# ──────────────────────────────────────────────────
phase2() {
  echo ""
  echo "═══════════════════════════════════════════════════"
  echo " Phase 2: Manual Single-Source Runs"
  echo "═══════════════════════════════════════════════════"

  local TEST_SOURCES=("pubmed" "epo_ops" "uniprot")

  for src in "${TEST_SOURCES[@]}"; do
    echo ""
    echo "--- Testing: $src ---"

    # Create a one-off job from the CronJob
    local job_name="test-${src//_/-}-$(date +%s)"
    echo "  Creating job: $job_name"
    kubectl -n "$NS" create job "$job_name" --from="cronjob/fetch-${src//_/-}" 2>/dev/null || {
      # Some CronJob names use different naming (e.g., epo_ops -> fetch-epo)
      local cronjob_name
      cronjob_name=$(kubectl -n "$NS" get cronjobs -o name 2>/dev/null | grep -E "fetch-${src//_/-}|fetch-${src%%_*}" | head -1 | sed 's|cronjob.batch/||')
      if [ -n "$cronjob_name" ]; then
        kubectl -n "$NS" create job "$job_name" --from="cronjob/$cronjob_name" 2>/dev/null || {
          fail "Could not create job for $src"
          continue
        }
      else
        fail "CronJob not found for $src"
        continue
      fi
    }

    # Wait for completion (5 min timeout)
    echo "  Waiting for job to complete (5 min timeout)..."
    if kubectl -n "$NS" wait --for=condition=complete "job/$job_name" --timeout=300s 2>/dev/null; then
      pass "Job completed successfully"
    else
      local status
      status=$(kubectl -n "$NS" get job "$job_name" -o jsonpath='{.status.conditions[0].type}' 2>/dev/null)
      fail "Job did not complete: $status"
      echo "  Logs:"
      kubectl -n "$NS" logs "job/$job_name" --tail=20 2>/dev/null | sed 's/^/    /'
      continue
    fi

    # Check meta.refresh_log
    local log_entry
    log_entry=$(run_sql "
      SELECT rl.status, rl.records_fetched, rl.records_inserted
      FROM meta.refresh_log rl
      JOIN meta.data_sources ds ON ds.source_id = rl.source_id
      WHERE ds.source_name = '$src'
      ORDER BY rl.refresh_completed_at DESC LIMIT 1
    ")
    if [ -n "$log_entry" ]; then
      pass "meta.refresh_log entry: $log_entry"
    else
      fail "No meta.refresh_log entry for $src"
    fi

    # Check last_successful_refresh updated
    local last_refresh
    last_refresh=$(run_sql "
      SELECT last_successful_refresh
      FROM meta.data_sources
      WHERE source_name = '$src'
    ")
    if [ -n "$last_refresh" ] && [ "$last_refresh" != "None" ]; then
      pass "last_successful_refresh: $last_refresh"
    else
      warn "last_successful_refresh not set (fetch may have returned 0 records)"
    fi

    # Print logs summary
    echo "  Job logs (last 5 lines):"
    kubectl -n "$NS" logs "job/$job_name" --tail=5 2>/dev/null | sed 's/^/    /'

    # Cleanup test job
    kubectl -n "$NS" delete job "$job_name" --ignore-not-found=true >/dev/null 2>&1 &
  done

  echo ""
  echo "Phase 2 complete. Failures: $FAILURES"
}

# ──────────────────────────────────────────────────
# Phase 3: Incremental validation (re-run same source)
# ──────────────────────────────────────────────────
phase3() {
  echo ""
  echo "═══════════════════════════════════════════════════"
  echo " Phase 3: Incremental Fetch Validation"
  echo "═══════════════════════════════════════════════════"
  echo ""
  echo "Re-running pubmed to verify incremental fetching."
  echo "Expected: logs show 'Last successful refresh for pubmed was X.X days ago'"
  echo ""

  local job_name="test-incremental-pubmed-$(date +%s)"
  kubectl -n "$NS" create job "$job_name" --from="cronjob/fetch-pubmed" 2>/dev/null || {
    fail "Could not create incremental test job"
    return
  }

  echo "  Waiting for job to complete..."
  if kubectl -n "$NS" wait --for=condition=complete "job/$job_name" --timeout=300s 2>/dev/null; then
    pass "Job completed"
  else
    fail "Job failed"
    kubectl -n "$NS" logs "job/$job_name" --tail=20 2>/dev/null | sed 's/^/    /'
    return
  fi

  # Check logs for incremental message
  local logs
  logs=$(kubectl -n "$NS" logs "job/$job_name" 2>/dev/null)

  if echo "$logs" | grep -q "Last successful refresh for pubmed was"; then
    pass "Incremental fetch detected prior refresh"
    echo "$logs" | grep "Last successful refresh" | sed 's/^/    /'
  elif echo "$logs" | grep -q "No prior refresh for pubmed"; then
    warn "Still using backfill window (Phase 2 may not have succeeded)"
  else
    fail "No incremental/backfill log message found"
  fi

  # Check record count didn't duplicate
  local counts
  counts=$(run_sql "
    SELECT rl.records_fetched, rl.records_inserted
    FROM meta.refresh_log rl
    JOIN meta.data_sources ds ON ds.source_id = rl.source_id
    WHERE ds.source_name = 'pubmed'
    ORDER BY rl.refresh_completed_at DESC LIMIT 2
  ")
  echo "  Last 2 refresh_log entries (records_fetched, records_inserted):"
  echo "$counts" | sed 's/^/    /'

  kubectl -n "$NS" delete job "$job_name" --ignore-not-found=true >/dev/null 2>&1 &

  echo ""
  echo "Phase 3 complete. Failures: $FAILURES"
}

# ──────────────────────────────────────────────────
# Status: Show CronJob schedule and last run
# ──────────────────────────────────────────────────
status() {
  echo ""
  echo "═══════════════════════════════════════════════════"
  echo " Ingestion CronJob Status"
  echo "═══════════════════════════════════════════════════"
  echo ""

  kubectl -n "$NS" get cronjobs -l app.kubernetes.io/component=ingestion \
    -o custom-columns='NAME:.metadata.name,SCHEDULE:.spec.schedule,SUSPEND:.spec.suspend,LAST:.status.lastScheduleTime' 2>/dev/null
}

# ──────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════"
echo " Staging Ingestion Pipeline Validation"
echo " Namespace: $NS"
echo " Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "══════════════════════════════════════════════════════"

case "$PHASE" in
  phase1)    phase1 ;;
  phase2)    phase2 ;;
  phase3)    phase3 ;;
  status)    status ;;
  all)
    phase1
    if [ "$FAILURES" -gt 0 ]; then
      echo ""
      echo -e "${RED}Phase 1 had $FAILURES failures. Fix before proceeding.${NC}"
      exit 1
    fi
    phase2
    phase3
    echo ""
    echo "══════════════════════════════════════════════════════"
    echo " Total failures: $FAILURES"
    echo "══════════════════════════════════════════════════════"
    if [ "$FAILURES" -gt 0 ]; then
      echo -e "${RED}Some checks failed. Review output above.${NC}"
      exit 1
    else
      echo -e "${GREEN}All checks passed.${NC}"
      echo "CronJobs are active and will fire on their next scheduled time."
    fi
    ;;
  *)
    echo "Usage: $0 {phase1|phase2|phase3|status|all}"
    exit 1
    ;;
esac
