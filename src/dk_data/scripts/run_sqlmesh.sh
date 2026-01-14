#!/bin/bash
# SQLMesh Runner Script
# Usage: ./run_sqlmesh.sh [command] [options]
#
# Commands:
#   plan      - Generate and preview a migration plan
#   apply     - Apply pending changes to the database
#   run       - Run the full transformation pipeline
#   audit     - Run data quality audits
#   test      - Run SQLMesh tests
#   clean     - Clean up state and start fresh
#
# Options:
#   --env     - Environment (dev, staging, prod). Default: dev
#   --start   - Start date for incremental models (YYYY-MM-DD)
#   --end     - End date for incremental models (YYYY-MM-DD)

set -e

# Navigate to sqlmesh directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQLMESH_DIR="$(dirname "$SCRIPT_DIR")/sqlmesh"

cd "$SQLMESH_DIR"

# Load environment variables
if [ -f "../.env.local" ]; then
    export $(grep -v '^#' ../.env.local | xargs)
fi

# Default values
COMMAND="${1:-run}"
ENV="${ENV:-dev}"
START_DATE=""
END_DATE=""

# Parse arguments
shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --start)
            START_DATE="$2"
            shift 2
            ;;
        --end)
            END_DATE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "SQLMesh Runner - TAVR Data Infrastructure"
echo "=============================================="
echo "Command: $COMMAND"
echo "Environment: $ENV"
echo "SQLMesh Directory: $SQLMESH_DIR"
echo ""

# Build date range arguments if provided
DATE_ARGS=""
if [ -n "$START_DATE" ]; then
    DATE_ARGS="--start $START_DATE"
fi
if [ -n "$END_DATE" ]; then
    DATE_ARGS="$DATE_ARGS --end $END_DATE"
fi

case $COMMAND in
    plan)
        echo "Generating migration plan..."
        sqlmesh plan $DATE_ARGS
        ;;

    apply)
        echo "Applying pending changes..."
        sqlmesh plan --auto-apply $DATE_ARGS
        ;;

    run)
        echo "Running transformation pipeline..."
        sqlmesh run $DATE_ARGS
        ;;

    audit)
        echo "Running data quality audits..."
        sqlmesh audit
        ;;

    test)
        echo "Running SQLMesh tests..."
        sqlmesh test
        ;;

    clean)
        echo "Cleaning SQLMesh state..."
        read -p "This will remove all SQLMesh state. Continue? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf .cache
            rm -rf logs
            echo "State cleaned."
        else
            echo "Cancelled."
        fi
        ;;

    info)
        echo "SQLMesh project info..."
        sqlmesh info
        ;;

    dag)
        echo "Generating DAG visualization..."
        sqlmesh dag
        ;;

    diff)
        echo "Showing model differences..."
        sqlmesh diff
        ;;

    *)
        echo "Unknown command: $COMMAND"
        echo ""
        echo "Usage: $0 [command] [options]"
        echo ""
        echo "Commands:"
        echo "  plan    - Generate and preview a migration plan"
        echo "  apply   - Apply pending changes to the database"
        echo "  run     - Run the full transformation pipeline"
        echo "  audit   - Run data quality audits"
        echo "  test    - Run SQLMesh tests"
        echo "  clean   - Clean up state and start fresh"
        echo "  info    - Show project information"
        echo "  dag     - Generate DAG visualization"
        echo "  diff    - Show model differences"
        exit 1
        ;;
esac

echo ""
echo "Done."
