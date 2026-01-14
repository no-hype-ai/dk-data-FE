#!/usr/bin/env bash
# Install TAVR Data Infrastructure cron jobs
#
# Usage: ./scripts/install_cron.sh [--dry-run]
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EDWARDS_HOME="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "TAVR Data Infrastructure - Cron Installer"
echo "=========================================="
echo ""

# Check for dry run
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
    echo ""
fi

# Verify we're in the right directory
if [[ ! -f "$EDWARDS_HOME/crontab.txt" ]]; then
    echo -e "${RED}ERROR: crontab.txt not found in $EDWARDS_HOME${NC}"
    exit 1
fi

# Check prerequisites
echo "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Python3: $(python3 --version)"

# Check PostgreSQL connection
if ! command -v psql &> /dev/null; then
    echo -e "${YELLOW}  ⚠ psql not found - database connection cannot be verified${NC}"
else
    echo -e "  ${GREEN}✓${NC} psql: $(psql --version | head -1)"
fi

# Check environment
echo ""
echo "Environment:"
echo "  EDWARDS_HOME=$EDWARDS_HOME"

# Create logs directory
echo ""
echo "Creating logs directory..."
mkdir -p "$EDWARDS_HOME/logs"
echo -e "  ${GREEN}✓${NC} Created: $EDWARDS_HOME/logs/"

# Generate crontab entries with correct path
echo ""
echo "Generating crontab entries..."

CRONTAB_ENTRIES=$(cat "$EDWARDS_HOME/crontab.txt" | \
    grep -v "^#" | \
    grep -v "^$" | \
    grep -v "^PATH=" | \
    grep -v "^EDWARDS_HOME=" | \
    sed "s|\$EDWARDS_HOME|$EDWARDS_HOME|g")

echo ""
echo "The following entries will be added to your crontab:"
echo "----------------------------------------"
echo "# TAVR Data Infrastructure - Auto-generated $(date +%Y-%m-%d)"
echo "EDWARDS_HOME=$EDWARDS_HOME"
echo ""
echo "$CRONTAB_ENTRIES"
echo "----------------------------------------"

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo -e "${YELLOW}DRY RUN: No changes made. Remove --dry-run to install.${NC}"
    exit 0
fi

# Confirm installation
echo ""
read -p "Install these cron jobs? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Backup existing crontab
BACKUP_FILE="/tmp/crontab_backup_$(date +%Y%m%d_%H%M%S)"
crontab -l > "$BACKUP_FILE" 2>/dev/null || true
echo -e "${GREEN}✓${NC} Backed up existing crontab to: $BACKUP_FILE"

# Install new crontab (appending to existing)
(
    crontab -l 2>/dev/null || true
    echo ""
    echo "# =================================================="
    echo "# TAVR Data Infrastructure - Auto-generated $(date +%Y-%m-%d)"
    echo "# =================================================="
    echo "EDWARDS_HOME=$EDWARDS_HOME"
    echo ""
    echo "$CRONTAB_ENTRIES"
) | crontab -

echo ""
echo -e "${GREEN}✓ Cron jobs installed successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify installation: crontab -l"
echo "  2. Check logs in: $EDWARDS_HOME/logs/"
echo "  3. Monitor via: curl localhost:3030/data_catalog"
echo ""
echo "To remove, run: crontab -e and delete the TAVR section"
