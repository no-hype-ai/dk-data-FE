#!/bin/bash
# Setup script for Dynamic Data Source Onboarding
# Run this after Docker containers are up

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Dynamic Data Source Onboarding Setup ==="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running. Please start Docker first."
    exit 1
fi

# Check if postgres container is running
if ! docker ps | grep -q "tavr-postgres\|postgres"; then
    echo "ERROR: PostgreSQL container is not running."
    echo "Run: cd $PROJECT_ROOT && docker compose up -d postgres"
    exit 1
fi

echo "1. Running migration 051_dynamic_transformation_config.sql..."
docker exec -i tavr-postgres psql -U postgres -d edwards_tavr < \
    "$PROJECT_ROOT/sql/migrations/051_dynamic_transformation_config.sql"

if [ $? -eq 0 ]; then
    echo "   Migration completed successfully!"
else
    echo "   ERROR: Migration failed!"
    exit 1
fi

echo ""
echo "2. Restarting PostgREST to expose bronze/silver schemas..."
cd "$PROJECT_ROOT" && docker compose restart postgrest 2>/dev/null || \
    docker restart tavr-postgrest 2>/dev/null || \
    echo "   NOTE: PostgREST container not found. Will be configured on next start."

echo ""
echo "3. Verifying setup..."

# Verify tables were created
TABLES=$(docker exec tavr-postgres psql -U postgres -d edwards_tavr -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'raw' AND table_name LIKE '%transformation%'")

if [ "$TABLES" -gt 0 ]; then
    echo "   Configuration tables created successfully!"
else
    echo "   WARNING: Configuration tables may not have been created properly."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Restart the job-trigger (FastAPI) service"
echo "  2. Access the API docs at: http://localhost:8000/docs"
echo "  3. Look for endpoints under '/data-platform' with tag 'dynamic-onboarding'"
echo ""
echo "Example: Register a new data source"
echo "  curl -X POST http://localhost:8000/data-platform/sources/register \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{"
echo "      \"source_name\": \"new_source\","
echo "      \"source_table\": \"bronze.new_source\","
echo "      \"column_mappings\": {\"inchi_key\": \"inchi_key\", \"name\": \"canonical_name\"}"
echo "    }'"
