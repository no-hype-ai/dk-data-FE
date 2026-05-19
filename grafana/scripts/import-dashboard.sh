#!/usr/bin/env bash
# import-dashboard.sh - Import dashboard JSON file to Grafana
# Vendored from dk-alchemy:grafana/scripts/import-dashboard.sh (plan.md §J.2 step 1).
# Usage: ./import-dashboard.sh <json-file> [folder-uid]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
source "$SCRIPT_DIR/lib/grafana-api.sh"

# ============================================================================
# Help
# ============================================================================

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] <json-file> [folder-uid]

Import a dashboard JSON file to Grafana.

Options:
  -h, --help       Show this help message
  -v, --verbose    Show detailed output
  -n, --dry-run    Show what would be done without making changes
  -m, --message    Commit message for dashboard version history

Arguments:
  json-file        Path to dashboard JSON file
  folder-uid       Target folder UID (auto-detected from metadata if not specified)

Examples:
  $(basename "$0") grafana/dashboards/cluster/cluster-overview.json
  $(basename "$0") grafana/dashboards/cluster/cluster-overview.json cluster
  $(basename "$0") --dry-run grafana/dashboards/cluster/cluster-overview.json
EOF
}

# ============================================================================
# Main
# ============================================================================

main() {
  local verbose=false
  local dry_run=false
  local message="Synced via GitOps"
  local json_file=""
  local folder_uid=""

  # Parse options
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      -v|--verbose)
        verbose=true
        export DEBUG=true
        shift
        ;;
      -n|--dry-run)
        dry_run=true
        shift
        ;;
      -m|--message)
        message="$2"
        shift 2
        ;;
      -*)
        error "Unknown option: $1"
        usage
        exit 1
        ;;
      *)
        if [[ -z "$json_file" ]]; then
          json_file="$1"
        elif [[ -z "$folder_uid" ]]; then
          folder_uid="$1"
        else
          error "Too many arguments"
          usage
          exit 1
        fi
        shift
        ;;
    esac
  done

  # Validate arguments
  if [[ -z "$json_file" ]]; then
    error "JSON file is required"
    usage
    exit 1
  fi

  if [[ ! -f "$json_file" ]]; then
    error "File not found: $json_file"
    exit 1
  fi

  # Check dependencies
  check_dependencies || exit 1

  # Extract dashboard info
  local uid
  uid=$(extract_uid "$json_file")

  local title
  title=$(extract_title "$json_file")

  # Get folder from metadata if not specified
  if [[ -z "$folder_uid" ]]; then
    folder_uid=$(extract_folder "$json_file")

    # If still empty, try to infer from directory
    if [[ -z "$folder_uid" ]]; then
      folder_uid=$(basename "$(dirname "$json_file")")
    fi
  fi

  info "Importing dashboard: $title ($uid)"
  info "Target folder: $folder_uid"

  if [[ "$dry_run" == "true" ]]; then
    info "[DRY RUN] Would import dashboard to Grafana"
    info "  File: $json_file"
    info "  UID: $uid"
    info "  Title: $title"
    info "  Folder: $folder_uid"
    exit 0
  fi

  # Verify connection
  verify_connection || exit 1

  # Ensure folder exists
  info "Ensuring folder exists: $folder_uid"
  local folder_title
  folder_title=$(echo "$folder_uid" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++)sub(/./,toupper(substr($i,1,1)),$i)}1')
  sync_folder "$folder_uid" "$folder_title" || {
    error "Failed to ensure folder exists"
    exit 1
  }

  # Import dashboard
  info "Uploading dashboard..."
  local result
  result=$(upsert_dashboard "$json_file" "$folder_uid" "$message") || {
    error "Failed to import dashboard"
    exit 1
  }

  # Extract result info
  local status
  status=$(echo "$result" | jq -r '.status // "unknown"')

  local version
  version=$(echo "$result" | jq -r '.version // 0')

  local url
  url=$(echo "$result" | jq -r '.url // ""')

  if [[ "$status" == "success" ]]; then
    success "Dashboard imported successfully"
    info "  Version: $version"
    info "  URL: ${GRAFANA_URL}${url}"
  else
    warn "Import completed with status: $status"
    echo "$result" | jq '.'
  fi
}

main "$@"
