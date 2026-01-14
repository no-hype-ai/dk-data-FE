#!/bin/bash
# TAVR Data Infrastructure - API Startup Script
# Starts PostgREST server for the API
#
# Usage:
#   ./start_api.sh [options]
#
# Options:
#   --port PORT    Override default port (3000)
#   --config FILE  Use custom config file
#   --check        Check configuration and exit
#   --daemon       Run in background

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${PROJECT_ROOT}/postgrest.conf"
PORT=3000
CHECK_ONLY=false
DAEMON=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --daemon)
            DAEMON=true
            shift
            ;;
        -h|--help)
            echo "TAVR Data Infrastructure - API Startup Script"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --port PORT    Override default port (3000)"
            echo "  --config FILE  Use custom config file"
            echo "  --check        Check configuration and exit"
            echo "  --daemon       Run in background"
            echo "  -h, --help     Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Load environment variables
if [ -f "${PROJECT_ROOT}/.env.local" ]; then
    export $(grep -v '^#' "${PROJECT_ROOT}/.env.local" | xargs)
fi

echo "=============================================="
echo "TAVR Data Infrastructure - API Server"
echo "=============================================="
echo "Config: ${CONFIG_FILE}"
echo "Port: ${PORT}"
echo ""

# Check if PostgREST is installed
if ! command -v postgrest &> /dev/null; then
    echo "ERROR: PostgREST is not installed."
    echo ""
    echo "Install with:"
    echo "  macOS:   brew install postgrest"
    echo "  Linux:   Download from https://github.com/PostgREST/postgrest/releases"
    echo "  Docker:  docker pull postgrest/postgrest"
    exit 1
fi

# Check if config file exists
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "ERROR: Config file not found: ${CONFIG_FILE}"
    exit 1
fi

# Check PostgreSQL connection
echo "Checking database connection..."
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5433}"
POSTGRES_DB="${POSTGRES_DB:-edwards_tavr}"

if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -d "${POSTGRES_DB}" &> /dev/null; then
    echo "ERROR: Cannot connect to PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}"
    echo "Make sure PostgreSQL is running and accessible."
    exit 1
fi
echo "Database connection: OK"

# Check if API schema exists
echo "Checking API schema..."
if ! psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -d "${POSTGRES_DB}" -c "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'api'" -t | grep -q 1; then
    echo "WARNING: API schema does not exist. Run init_database.sql first."
fi

# Check if views exist
echo "Checking API views..."
VIEWS=$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -d "${POSTGRES_DB}" -c "SELECT table_name FROM information_schema.views WHERE table_schema = 'api'" -t)
if [ -z "$VIEWS" ]; then
    echo "WARNING: No views found in api schema."
else
    echo "Available endpoints:"
    for view in $VIEWS; do
        echo "  - GET /${view}"
    done
fi
echo ""

# Configuration check only
if [ "$CHECK_ONLY" = true ]; then
    echo "Configuration check complete."
    exit 0
fi

# Create temporary config with port override
if [ "$PORT" != "3000" ]; then
    TEMP_CONFIG=$(mktemp)
    sed "s/server-port = .*/server-port = ${PORT}/" "${CONFIG_FILE}" > "${TEMP_CONFIG}"
    CONFIG_FILE="${TEMP_CONFIG}"
fi

# Start PostgREST
if [ "$DAEMON" = true ]; then
    echo "Starting PostgREST in background..."
    nohup postgrest "${CONFIG_FILE}" > "${PROJECT_ROOT}/logs/postgrest.log" 2>&1 &
    PID=$!
    echo "PostgREST started with PID: ${PID}"
    echo "Logs: ${PROJECT_ROOT}/logs/postgrest.log"

    # Wait a moment and check if it's running
    sleep 2
    if kill -0 $PID 2>/dev/null; then
        echo ""
        echo "API Server running at: http://localhost:${PORT}"
        echo ""
        echo "Example requests:"
        echo "  curl http://localhost:${PORT}/targets"
        echo "  curl http://localhost:${PORT}/targets?tier_classification=eq.A"
        echo "  curl http://localhost:${PORT}/hospitals?state=eq.CA"
    else
        echo "ERROR: PostgREST failed to start. Check logs."
        exit 1
    fi
else
    echo "Starting PostgREST..."
    echo "Press Ctrl+C to stop"
    echo ""
    echo "API Server running at: http://localhost:${PORT}"
    echo ""
    postgrest "${CONFIG_FILE}"
fi
