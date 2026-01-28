#!/bin/bash
# Check for duplicate files in the repository
# Feature: 002-production-readiness
# Task: T037
#
# This script verifies that files exist in exactly one canonical location.
# It should be run in CI to prevent accidental reintroduction of duplicates.
#
# Exit codes:
#   0 - No duplicates found
#   1 - Duplicates detected

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
ERRORS=0

echo "Checking for duplicate files..."
echo "Repository root: $REPO_ROOT"
echo ""

# Function to check if a directory exists and has files
check_dir_should_not_exist() {
    local dir="$1"
    local canonical="$2"

    if [ -d "$REPO_ROOT/$dir" ]; then
        # Check if directory has actual files (not just .gitkeep)
        local file_count
        file_count=$(find "$REPO_ROOT/$dir" -type f ! -name '.gitkeep' ! -name 'README.md' | wc -l | tr -d ' ')

        if [ "$file_count" -gt 0 ]; then
            echo "ERROR: Duplicate directory found: /$dir/"
            echo "       Canonical location: $canonical"
            echo "       Found $file_count file(s) that should be removed or merged"
            find "$REPO_ROOT/$dir" -type f ! -name '.gitkeep' ! -name 'README.md' | head -5
            ERRORS=$((ERRORS + 1))
        fi
    fi
}

# Function to check file doesn't exist in multiple locations
check_file_unique() {
    local filename="$1"
    local expected_location="$2"

    local locations
    locations=$(find "$REPO_ROOT" -name "$filename" -type f ! -path "*/.venv/*" ! -path "*/node_modules/*" ! -path "*/__pycache__/*" 2>/dev/null | grep -v "$expected_location" || true)

    if [ -n "$locations" ]; then
        echo "ERROR: File '$filename' found in multiple locations:"
        echo "       Expected: $expected_location"
        echo "       Also found:"
        echo "$locations" | sed 's/^/         /'
        ERRORS=$((ERRORS + 1))
    fi
}

# Check for duplicate script directories
check_dir_should_not_exist "scripts/data" "src/dk_data/scripts/"
check_dir_should_not_exist "scripts/ops" "src/dk_data/scripts/"
check_dir_should_not_exist "scripts/utils" "src/dk_data/scripts/"

# Check for duplicate SQL directories
check_dir_should_not_exist "sql" "src/dk_data/sql/"

# Check for duplicate config files
check_file_unique "docker-compose.yml" "docker-compose.yml"
check_file_unique "docker-compose.prod.yml" "docker-compose.prod.yml"

# Check that src/dk_data doesn't have its own docker-compose files
if [ -f "$REPO_ROOT/src/dk_data/docker-compose.yml" ]; then
    echo "ERROR: docker-compose.yml found in src/dk_data/ - should only exist at repository root"
    ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
if [ $ERRORS -gt 0 ]; then
    echo "FAILED: Found $ERRORS duplicate file issue(s)"
    echo ""
    echo "To fix:"
    echo "  1. Ensure files exist in their canonical location"
    echo "  2. Remove duplicates from non-canonical locations"
    echo "  3. Update any references to use canonical paths"
    exit 1
else
    echo "PASSED: No duplicate files detected"
    exit 0
fi
