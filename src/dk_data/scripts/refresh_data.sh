#!/bin/bash
# TAVR Data Infrastructure - Data Refresh Orchestration Script
# Orchestrates the complete data refresh pipeline
#
# Usage:
#   ./refresh_data.sh [options]
#
# Options:
#   --source SOURCE   Refresh specific source only
#   --skip-ingest     Skip ingestion, run transforms only
#   --skip-transform  Skip transforms, run ingestion only
#   --dry-run         Show what would be done without executing
#   --verbose         Enable verbose logging

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/refresh_$(date +%Y%m%d_%H%M%S).log"

# Options
SOURCE=""
SKIP_INGEST=false
SKIP_TRANSFORM=false
DRY_RUN=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --source)
            SOURCE="$2"
            shift 2
            ;;
        --skip-ingest)
            SKIP_INGEST=true
            shift
            ;;
        --skip-transform)
            SKIP_TRANSFORM=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "TAVR Data Infrastructure - Data Refresh Script"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --source SOURCE   Refresh specific source only"
            echo "  --skip-ingest     Skip ingestion, run transforms only"
            echo "  --skip-transform  Skip transforms, run ingestion only"
            echo "  --dry-run         Show what would be done"
            echo "  --verbose, -v     Enable verbose logging"
            echo "  -h, --help        Show this help"
            echo ""
            echo "Sources: cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc, hrsa"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

# Load environment variables
if [ -f "${PROJECT_ROOT}/.env.local" ]; then
    export $(grep -v '^#' "${PROJECT_ROOT}/.env.local" | xargs)
fi

echo "=============================================="
echo "TAVR Data Infrastructure - Data Refresh"
echo "=============================================="
echo "Start Time: $(date)"
echo "Log File: ${LOG_FILE}"
echo ""

log "INFO" "Starting data refresh pipeline"

# Check database connection
log "INFO" "Checking database connection..."
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
POSTGRES_DB="${POSTGRES_DB:-dk_data}"

if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -d "${POSTGRES_DB}" &> /dev/null; then
    log "ERROR" "Cannot connect to PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}"
    exit 1
fi
log "INFO" "Database connection OK"

# Define refresh functions
refresh_source() {
    local source_name="$1"
    local data_file="$2"
    local extra_args="$3"

    log "INFO" "Refreshing source: ${source_name}"

    if [ "$DRY_RUN" = true ]; then
        log "INFO" "[DRY RUN] Would refresh ${source_name}"
        return 0
    fi

    cd "${PROJECT_ROOT}"

    local cmd="python -m ingestion.main ${source_name}"
    if [ -n "$data_file" ]; then
        cmd="${cmd} --file ${data_file}"
    fi
    if [ -n "$extra_args" ]; then
        cmd="${cmd} ${extra_args}"
    fi
    if [ "$VERBOSE" = true ]; then
        cmd="${cmd} --verbose"
    fi

    log "INFO" "Running: ${cmd}"

    if eval "${cmd}" >> "${LOG_FILE}" 2>&1; then
        log "INFO" "Successfully refreshed ${source_name}"
        return 0
    else
        log "ERROR" "Failed to refresh ${source_name}"
        return 1
    fi
}

run_transforms() {
    log "INFO" "Running SQLMesh transformations..."

    if [ "$DRY_RUN" = true ]; then
        log "INFO" "[DRY RUN] Would run SQLMesh transforms"
        return 0
    fi

    cd "${PROJECT_ROOT}/sqlmesh"

    if "${SCRIPT_DIR}/run_sqlmesh.sh" run >> "${LOG_FILE}" 2>&1; then
        log "INFO" "SQLMesh transformations completed"
        return 0
    else
        log "ERROR" "SQLMesh transformations failed"
        return 1
    fi
}

run_quality_checks() {
    log "INFO" "Running data quality checks..."

    if [ "$DRY_RUN" = true ]; then
        log "INFO" "[DRY RUN] Would run quality checks"
        return 0
    fi

    cd "${PROJECT_ROOT}"

    if python "${SCRIPT_DIR}/check_freshness.py" >> "${LOG_FILE}" 2>&1; then
        log "INFO" "Quality checks completed"
        return 0
    else
        log "WARN" "Quality checks reported issues"
        return 0  # Don't fail pipeline on quality warnings
    fi
}

# Main execution
ERRORS=0

# Step 1: Ingestion
if [ "$SKIP_INGEST" = false ]; then
    log "INFO" "=== PHASE 1: DATA INGESTION ==="

    if [ -n "$SOURCE" ]; then
        # Refresh specific source
        case "$SOURCE" in
            cms_inpatient)
                refresh_source "cms_inpatient" "${DATA_DIR:-data}/cms_inpatient.csv" "--fiscal-year 2023" || ((ERRORS++))
                ;;
            cms_hospital_info)
                refresh_source "cms_hospital_info" "${DATA_DIR:-data}/hospital_info.csv" || ((ERRORS++))
                ;;
            cms_cost_reports)
                refresh_source "cms_cost_reports" "${DATA_DIR:-data}/cost_reports.csv" || ((ERRORS++))
                ;;
            acc_tvc)
                refresh_source "acc_tvc" "${DATA_DIR:-data}/acc_tvc.csv" || ((ERRORS++))
                ;;
            hrsa)
                refresh_source "hrsa" "" || ((ERRORS++))
                ;;
            *)
                log "ERROR" "Unknown source: ${SOURCE}"
                exit 1
                ;;
        esac
    else
        # Refresh all sources
        log "INFO" "Refreshing all data sources..."

        # HRSA is API-based, can run without files
        refresh_source "hrsa" "" || ((ERRORS++))

        # File-based sources - check if data files exist
        if [ -f "${DATA_DIR:-data}/cms_inpatient.csv" ]; then
            refresh_source "cms_inpatient" "${DATA_DIR:-data}/cms_inpatient.csv" "--fiscal-year 2023" || ((ERRORS++))
        else
            log "WARN" "Skipping cms_inpatient: data file not found"
        fi

        if [ -f "${DATA_DIR:-data}/hospital_info.csv" ]; then
            refresh_source "cms_hospital_info" "${DATA_DIR:-data}/hospital_info.csv" || ((ERRORS++))
        else
            log "WARN" "Skipping cms_hospital_info: data file not found"
        fi

        if [ -f "${DATA_DIR:-data}/cost_reports.csv" ]; then
            refresh_source "cms_cost_reports" "${DATA_DIR:-data}/cost_reports.csv" || ((ERRORS++))
        else
            log "WARN" "Skipping cms_cost_reports: data file not found"
        fi

        if [ -f "${DATA_DIR:-data}/acc_tvc.csv" ]; then
            refresh_source "acc_tvc" "${DATA_DIR:-data}/acc_tvc.csv" || ((ERRORS++))
        else
            log "WARN" "Skipping acc_tvc: data file not found"
        fi
    fi
else
    log "INFO" "Skipping ingestion (--skip-ingest)"
fi

# Step 2: Transformations
if [ "$SKIP_TRANSFORM" = false ]; then
    log "INFO" "=== PHASE 2: DATA TRANSFORMATION ==="
    run_transforms || ((ERRORS++))
else
    log "INFO" "Skipping transforms (--skip-transform)"
fi

# Step 3: Quality Checks
log "INFO" "=== PHASE 3: QUALITY CHECKS ==="
run_quality_checks

# Summary
echo ""
echo "=============================================="
echo "Refresh Complete"
echo "=============================================="
echo "End Time: $(date)"
echo "Errors: ${ERRORS}"
echo "Log File: ${LOG_FILE}"
echo ""

if [ $ERRORS -gt 0 ]; then
    log "ERROR" "Refresh completed with ${ERRORS} errors"
    exit 1
else
    log "INFO" "Refresh completed successfully"
    exit 0
fi
