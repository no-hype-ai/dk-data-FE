#!/usr/bin/env bash
# sync-all.sh - Sync all Grafana resources from repository
# Vendored from dk-alchemy:grafana/scripts/sync-all.sh (plan.md §J.2 step 1).
# Bugfixes should land upstream and be re-vendored here.
# Usage: ./sync-all.sh [OPTIONS]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
source "$SCRIPT_DIR/lib/grafana-api.sh"

# ============================================================================
# Configuration
# ============================================================================

SYNC_FOLDERS=true
SYNC_DASHBOARDS=true
SYNC_ALERTS=true

FOLDERS_SYNCED=0
DASHBOARDS_SYNCED=0
ALERTS_SYNCED=0
ERRORS=0

# ============================================================================
# Help
# ============================================================================

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Sync all Grafana resources (folders, dashboards, alerts) to Grafana.

Options:
  -h, --help           Show this help message
  -v, --verbose        Show detailed output
  -n, --dry-run        Show what would be done without making changes
  -f, --force          Force sync even if resources appear unchanged
  --folders-only       Only sync folders
  --dashboards-only    Only sync dashboards
  --alerts-only        Only sync alerts
  --no-folders         Skip folder sync
  --no-dashboards      Skip dashboard sync
  --no-alerts          Skip alert sync

Examples:
  $(basename "$0")                    # Sync everything
  $(basename "$0") --dry-run          # Preview changes
  $(basename "$0") --dashboards-only  # Only sync dashboards
  $(basename "$0") --force            # Force full resync
EOF
}

# ============================================================================
# Sync Functions
# ============================================================================

# Sync folders from folders.yaml
sync_folders_from_file() {
  local folders_file="$GRAFANA_DIR/folders/folders.yaml"

  if [[ ! -f "$folders_file" ]]; then
    warn "Folders file not found: $folders_file"
    return 0
  fi

  info "Syncing folders..."

  local folders
  folders=$(yq eval '.folders // []' "$folders_file" -o=json)

  echo "$folders" | jq -c '.[]' | while read -r folder; do
    local uid
    uid=$(echo "$folder" | jq -r '.uid')
    local title
    title=$(echo "$folder" | jq -r '.title')

    if [[ "$DRY_RUN" == "true" ]]; then
      info "[DRY RUN] Would sync folder: $title ($uid)"
    else
      if sync_folder "$uid" "$title"; then
        success "Synced folder: $title ($uid)"
        echo "1" >> /tmp/sync_folders_count_$$
      else
        error "Failed to sync folder: $title ($uid)"
        echo "1" >> /tmp/sync_errors_$$
      fi
    fi
  done

  # Count results from subshell
  if [[ -f /tmp/sync_folders_count_$$ ]]; then
    FOLDERS_SYNCED=$(wc -l < /tmp/sync_folders_count_$$ | tr -d ' ')
    rm -f /tmp/sync_folders_count_$$
  fi
}

# Sync all dashboards
sync_dashboards_from_dir() {
  info "Syncing dashboards..."

  local dashboard_dir="$GRAFANA_DIR/dashboards"

  if [[ ! -d "$dashboard_dir" ]]; then
    warn "Dashboards directory not found: $dashboard_dir"
    return 0
  fi

  # Find all JSON files (excluding _config.yaml)
  while IFS= read -r -d '' file; do
    local filename
    filename=$(basename "$file")

    # Skip config files
    if [[ "$filename" == "_config.yaml" ]] || [[ "$filename" == "README.md" ]]; then
      continue
    fi

    # Extract folder from directory structure
    local folder_uid
    folder_uid=$(basename "$(dirname "$file")")

    # Skip if it's the top-level dashboards directory
    if [[ "$folder_uid" == "dashboards" ]]; then
      folder_uid=""
    fi

    local uid
    uid=$(extract_uid "$file" 2>/dev/null || basename "$file" .json)

    local title
    title=$(extract_title "$file" 2>/dev/null || "$uid")

    if [[ "$DRY_RUN" == "true" ]]; then
      info "[DRY RUN] Would sync dashboard: $title ($uid) -> $folder_uid"
    else
      debug "Syncing dashboard: $file"

      if upsert_dashboard "$file" "$folder_uid" "Synced via GitOps" &>/dev/null; then
        success "Synced dashboard: $title ($uid)"
        ((DASHBOARDS_SYNCED++)) || true
      else
        error "Failed to sync dashboard: $title ($uid)"
        ((ERRORS++)) || true
      fi
    fi
  done < <(find "$dashboard_dir" -name "*.json" -type f -print0 2>/dev/null)
}

# Sync all alerts
sync_alerts_from_dir() {
  info "Syncing alerts..."

  local alerts_dir="$GRAFANA_DIR/alerts"

  if [[ ! -d "$alerts_dir" ]]; then
    warn "Alerts directory not found: $alerts_dir"
    return 0
  fi

  # Find all YAML files (excluding _config.yaml)
  while IFS= read -r -d '' file; do
    local filename
    filename=$(basename "$file")

    # Skip config files
    if [[ "$filename" == "_config.yaml" ]]; then
      continue
    fi

    debug "Processing alert file: $file"

    # Read alert file and convert to JSON
    local alert_json
    alert_json=$(yq eval -o=json "$file")

    # Process each group
    echo "$alert_json" | jq -c '.groups // [] | .[]' | while read -r group; do
      local group_name folder_name org_id interval
      group_name=$(echo "$group" | jq -r '.name // "Default"')
      folder_name=$(echo "$group" | jq -r '.folder // "Alerts"')
      org_id=$(echo "$group" | jq -r '.orgId // 1')
      interval=$(echo "$group" | jq -r '.interval // "1m"')

      # Get folder UID (lowercase folder name is used as UID)
      local folder_uid
      folder_uid=$(echo "$folder_name" | tr '[:upper:]' '[:lower:]')

      debug "Processing group: $group_name (folder: $folder_uid)"

      # Process each rule in the group
      echo "$group" | jq -c '.rules // [] | .[]' | while read -r rule; do
        local rule_uid rule_title
        rule_uid=$(echo "$rule" | jq -r '.uid')
        rule_title=$(echo "$rule" | jq -r '.title')

        if [[ "$DRY_RUN" == "true" ]]; then
          info "[DRY RUN] Would sync alert rule: $rule_title ($rule_uid)"
          echo "1" >> /tmp/sync_alerts_count_$$
        else
          debug "Syncing alert rule: $rule_title ($rule_uid)"

          # Build Grafana Provisioning API format
          local rule_json
          rule_json=$(echo "$rule" | jq --arg folder "$folder_uid" --arg group "$group_name" --argjson orgId "$org_id" '{
            uid: .uid,
            title: .title,
            orgID: $orgId,
            folderUID: $folder,
            ruleGroup: $group,
            condition: .condition,
            data: .data,
            noDataState: (.noDataState // "NoData"),
            execErrState: (.execErrState // "Error"),
            for: .for,
            labels: (.labels // {}),
            annotations: (.annotations // {})
          }')

          if upsert_alert_rule "$rule_json" &>/dev/null; then
            success "Synced alert rule: $rule_title ($rule_uid)"
            echo "1" >> /tmp/sync_alerts_count_$$
          else
            error "Failed to sync alert rule: $rule_title ($rule_uid)"
            echo "1" >> /tmp/sync_errors_$$
          fi
        fi
      done
    done
  done < <(find "$alerts_dir" -name "*.yaml" -type f -print0 2>/dev/null)

  # Count results from subshell
  if [[ -f /tmp/sync_alerts_count_$$ ]]; then
    ALERTS_SYNCED=$(wc -l < /tmp/sync_alerts_count_$$ | tr -d ' ')
    rm -f /tmp/sync_alerts_count_$$
  fi
}

# ============================================================================
# Main
# ============================================================================

main() {
  local verbose=false
  DRY_RUN=false
  local force=false

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
        DRY_RUN=true
        shift
        ;;
      -f|--force)
        force=true
        shift
        ;;
      --folders-only)
        SYNC_DASHBOARDS=false
        SYNC_ALERTS=false
        shift
        ;;
      --dashboards-only)
        SYNC_FOLDERS=false
        SYNC_ALERTS=false
        shift
        ;;
      --alerts-only)
        SYNC_FOLDERS=false
        SYNC_DASHBOARDS=false
        shift
        ;;
      --no-folders)
        SYNC_FOLDERS=false
        shift
        ;;
      --no-dashboards)
        SYNC_DASHBOARDS=false
        shift
        ;;
      --no-alerts)
        SYNC_ALERTS=false
        shift
        ;;
      -*)
        error "Unknown option: $1"
        usage
        exit 1
        ;;
      *)
        error "Unexpected argument: $1"
        usage
        exit 1
        ;;
    esac
  done

  # Check dependencies
  check_dependencies || exit 1

  info "Starting Grafana sync"
  info "  Grafana URL: $GRAFANA_URL"
  info "  Dry run: $DRY_RUN"
  echo

  if [[ "$DRY_RUN" != "true" ]]; then
    # Verify connection
    verify_connection || exit 1
    echo
  fi

  # Clean up any leftover temp files
  rm -f /tmp/sync_*_$$

  # Sync folders first (dashboards depend on folders)
  if [[ "$SYNC_FOLDERS" == "true" ]]; then
    sync_folders_from_file
    echo
  fi

  # Sync dashboards
  if [[ "$SYNC_DASHBOARDS" == "true" ]]; then
    sync_dashboards_from_dir
    echo
  fi

  # Sync alerts
  if [[ "$SYNC_ALERTS" == "true" ]]; then
    sync_alerts_from_dir
    echo
  fi

  # Count errors from subshell
  if [[ -f /tmp/sync_errors_$$ ]]; then
    local subshell_errors
    subshell_errors=$(wc -l < /tmp/sync_errors_$$ | tr -d ' ')
    ERRORS=$((ERRORS + subshell_errors))
    rm -f /tmp/sync_errors_$$
  fi

  # Summary
  echo "=================================="
  echo "Sync Summary"
  echo "=================================="
  if [[ "$SYNC_FOLDERS" == "true" ]]; then
    echo "Folders synced: $FOLDERS_SYNCED"
  fi
  if [[ "$SYNC_DASHBOARDS" == "true" ]]; then
    echo "Dashboards synced: $DASHBOARDS_SYNCED"
  fi
  if [[ "$SYNC_ALERTS" == "true" ]]; then
    echo "Alerts synced: $ALERTS_SYNCED"
  fi
  echo "Errors: $ERRORS"
  echo

  if [[ $ERRORS -gt 0 ]]; then
    error "Sync completed with $ERRORS error(s)"
    exit 1
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    info "Dry run completed. No changes were made."
  else
    success "Sync completed successfully"
  fi
}

main "$@"
