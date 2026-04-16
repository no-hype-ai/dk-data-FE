#!/usr/bin/env bash
# validate.sh - Validate Grafana dashboards and alerts
# Vendored from dk-alchemy:grafana/scripts/validate.sh (plan.md §J.2 step 1).
# Usage: ./validate.sh [directory]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAFANA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source shared library
source "$SCRIPT_DIR/lib/grafana-api.sh"

# ============================================================================
# Configuration
# ============================================================================

ERRORS=0
WARNINGS=0
VALIDATED=0

# ============================================================================
# Help
# ============================================================================

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [directory]

Validate Grafana dashboard JSON and alert YAML files.

Options:
  -h, --help     Show this help message
  -v, --verbose  Show detailed validation output
  -s, --strict   Treat warnings as errors

Arguments:
  directory      Directory to validate (default: grafana/)

Examples:
  $(basename "$0")                           # Validate all
  $(basename "$0") grafana/dashboards        # Validate dashboards only
  $(basename "$0") grafana/alerts            # Validate alerts only
  $(basename "$0") -v grafana/dashboards/cluster  # Verbose validation
EOF
}

# ============================================================================
# Validation Functions
# ============================================================================

# Validate JSON syntax
validate_json_syntax() {
  local file="$1"
  if ! jq empty "$file" 2>/dev/null; then
    error "Invalid JSON syntax: $file"
    return 1
  fi
  return 0
}

# Validate YAML syntax
validate_yaml_syntax() {
  local file="$1"
  if ! yq eval '.' "$file" &>/dev/null; then
    error "Invalid YAML syntax: $file"
    return 1
  fi
  return 0
}

# Validate dashboard JSON file
validate_dashboard() {
  local file="$1"
  local errors=0
  local filename
  filename=$(basename "$file" .json)

  debug "Validating dashboard: $file"

  # Check JSON syntax
  if ! validate_json_syntax "$file"; then
    errors=$((errors + 1))
    return 1
  fi

  # Determine if file has metadata wrapper
  local has_metadata=false
  if jq -e '.__metadata' "$file" &>/dev/null; then
    has_metadata=true
  fi

  # Extract dashboard object
  local dashboard
  if [[ "$has_metadata" == "true" ]]; then
    dashboard=$(jq '.dashboard' "$file")
  else
    dashboard=$(cat "$file")
  fi

  # Check required fields: uid
  local uid
  uid=$(echo "$dashboard" | jq -r '.uid // empty')
  if [[ -z "$uid" ]]; then
    error "Missing required field 'uid': $file"
    errors=$((errors + 1))
  fi

  # Check required fields: title
  local title
  title=$(echo "$dashboard" | jq -r '.title // empty')
  if [[ -z "$title" ]]; then
    error "Missing required field 'title': $file"
    errors=$((errors + 1))
  fi

  # Check required fields: panels
  local panel_count
  panel_count=$(echo "$dashboard" | jq '.panels | length // 0')
  if [[ "$panel_count" -eq 0 ]]; then
    error "Dashboard has no panels: $file"
    errors=$((errors + 1))
  fi

  # Validate uid matches filename
  if [[ -n "$uid" ]] && [[ "$uid" != "$filename" ]]; then
    warn "UID '$uid' does not match filename '$filename': $file"
    WARNINGS=$((WARNINGS + 1))
  fi

  # Validate folder metadata matches directory
  if [[ "$has_metadata" == "true" ]]; then
    local metadata_folder
    metadata_folder=$(jq -r '.__metadata.folder // empty' "$file" | tr '[:upper:]' '[:lower:]')
    local dir_name
    dir_name=$(basename "$(dirname "$file")")

    if [[ -n "$metadata_folder" ]] && [[ "$metadata_folder" != "$dir_name" ]]; then
      warn "Metadata folder '$metadata_folder' does not match directory '$dir_name': $file"
      WARNINGS=$((WARNINGS + 1))
    fi
  fi

  # Check for hardcoded datasource UIDs (should use variables)
  local hardcoded_datasources
  hardcoded_datasources=$(echo "$dashboard" | jq -r '.panels[].datasource.uid? // empty' | grep -vE '^\$\{|^$' || true)
  if [[ -n "$hardcoded_datasources" ]]; then
    warn "Dashboard contains hardcoded datasource UIDs (use \${datasource} variable): $file"
    WARNINGS=$((WARNINGS + 1))
  fi

  if [[ $errors -gt 0 ]]; then
    return 1
  fi

  return 0
}

# Validate alert YAML file
validate_alert() {
  local file="$1"
  local errors=0

  debug "Validating alert: $file"

  # Check YAML syntax
  if ! validate_yaml_syntax "$file"; then
    errors=$((errors + 1))
    return 1
  fi

  # Check apiVersion
  local api_version
  api_version=$(yq eval '.apiVersion // 0' "$file")
  if [[ "$api_version" != "1" ]]; then
    error "Invalid or missing 'apiVersion' (expected: 1): $file"
    errors=$((errors + 1))
  fi

  # Check groups exist
  local group_count
  group_count=$(yq eval '.groups | length // 0' "$file")
  if [[ "$group_count" -eq 0 ]]; then
    error "No alert groups defined: $file"
    errors=$((errors + 1))
  fi

  # Validate each rule in each group
  local groups
  groups=$(yq eval '.groups // []' "$file" -o=json)

  echo "$groups" | jq -c '.[]' | while read -r group; do
    local group_name
    group_name=$(echo "$group" | jq -r '.name // "unnamed"')

    echo "$group" | jq -c '.rules // [] | .[]' | while read -r rule; do
      local rule_uid
      rule_uid=$(echo "$rule" | jq -r '.uid // empty')
      local rule_title
      rule_title=$(echo "$rule" | jq -r '.title // empty')

      # Check required fields
      if [[ -z "$rule_uid" ]]; then
        error "Alert rule missing 'uid' in group '$group_name': $file"
        echo "1" >> /tmp/validate_errors_$$
      fi

      if [[ -z "$rule_title" ]]; then
        error "Alert rule missing 'title' in group '$group_name': $file"
        echo "1" >> /tmp/validate_errors_$$
      fi

      # Check condition
      local condition
      condition=$(echo "$rule" | jq -r '.condition // empty')
      if [[ -z "$condition" ]]; then
        error "Alert rule '$rule_uid' missing 'condition': $file"
        echo "1" >> /tmp/validate_errors_$$
      fi

      # Check severity label
      local severity
      severity=$(echo "$rule" | jq -r '.labels.severity // empty')
      if [[ -z "$severity" ]]; then
        warn "Alert rule '$rule_uid' missing 'severity' label: $file"
        echo "W" >> /tmp/validate_warnings_$$
      elif [[ ! "$severity" =~ ^(critical|warning|info)$ ]]; then
        error "Alert rule '$rule_uid' has invalid severity '$severity' (expected: critical, warning, info): $file"
        echo "1" >> /tmp/validate_errors_$$
      fi
    done
  done

  # Count errors from subshell
  if [[ -f /tmp/validate_errors_$$ ]]; then
    local subshell_errors
    subshell_errors=$(wc -l < /tmp/validate_errors_$$ | tr -d ' ')
    errors=$((errors + subshell_errors))
    rm -f /tmp/validate_errors_$$
  fi

  if [[ -f /tmp/validate_warnings_$$ ]]; then
    local subshell_warnings
    subshell_warnings=$(wc -l < /tmp/validate_warnings_$$ | tr -d ' ')
    WARNINGS=$((WARNINGS + subshell_warnings))
    rm -f /tmp/validate_warnings_$$
  fi

  if [[ $errors -gt 0 ]]; then
    return 1
  fi

  return 0
}

# Validate folders.yaml
validate_folders() {
  local file="$1"
  local errors=0

  debug "Validating folders: $file"

  # Check YAML syntax
  if ! validate_yaml_syntax "$file"; then
    errors=$((errors + 1))
    return 1
  fi

  # Check apiVersion
  local api_version
  api_version=$(yq eval '.apiVersion // 0' "$file")
  if [[ "$api_version" != "1" ]]; then
    error "Invalid or missing 'apiVersion' (expected: 1): $file"
    errors=$((errors + 1))
  fi

  # Check folders exist
  local folder_count
  folder_count=$(yq eval '.folders | length // 0' "$file")
  if [[ "$folder_count" -eq 0 ]]; then
    error "No folders defined: $file"
    errors=$((errors + 1))
  fi

  # Validate each folder
  local folders
  folders=$(yq eval '.folders // []' "$file" -o=json)

  local seen_uids=""
  echo "$folders" | jq -c '.[]' | while read -r folder; do
    local uid
    uid=$(echo "$folder" | jq -r '.uid // empty')
    local title
    title=$(echo "$folder" | jq -r '.title // empty')

    if [[ -z "$uid" ]]; then
      error "Folder missing 'uid': $file"
      echo "1" >> /tmp/validate_errors_$$
    fi

    if [[ -z "$title" ]]; then
      error "Folder '$uid' missing 'title': $file"
      echo "1" >> /tmp/validate_errors_$$
    fi

    # Check uid format (lowercase, alphanumeric, hyphens)
    if [[ -n "$uid" ]] && ! [[ "$uid" =~ ^[a-z0-9-]+$ ]]; then
      error "Folder uid '$uid' must be lowercase alphanumeric with hyphens: $file"
      echo "1" >> /tmp/validate_errors_$$
    fi
  done

  # Count errors from subshell
  if [[ -f /tmp/validate_errors_$$ ]]; then
    local subshell_errors
    subshell_errors=$(wc -l < /tmp/validate_errors_$$ | tr -d ' ')
    errors=$((errors + subshell_errors))
    rm -f /tmp/validate_errors_$$
  fi

  if [[ $errors -gt 0 ]]; then
    return 1
  fi

  return 0
}

# ============================================================================
# Main
# ============================================================================

main() {
  local verbose=false
  local strict=false
  local target_dir="$GRAFANA_DIR"

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
      -s|--strict)
        strict=true
        shift
        ;;
      -*)
        error "Unknown option: $1"
        usage
        exit 1
        ;;
      *)
        target_dir="$1"
        shift
        ;;
    esac
  done

  # Check dependencies (only jq and yq needed for validation)
  if ! command -v jq &>/dev/null; then
    error "jq is required. Install with: brew install jq"
    exit 1
  fi

  if ! command -v yq &>/dev/null; then
    error "yq is required. Install with: brew install yq"
    exit 1
  fi

  info "Validating Grafana resources in: $target_dir"
  echo

  # Validate dashboards
  if [[ -d "$target_dir/dashboards" ]] || [[ "$target_dir" == *dashboards* ]]; then
    local dashboard_dir="$target_dir"
    if [[ -d "$target_dir/dashboards" ]]; then
      dashboard_dir="$target_dir/dashboards"
    fi

    info "Validating dashboards..."
    while IFS= read -r -d '' file; do
      # Skip _config.yaml
      if [[ "$(basename "$file")" == "_config.yaml" ]]; then
        continue
      fi

      if validate_dashboard "$file"; then
        success "$(basename "$file")"
        VALIDATED=$((VALIDATED + 1))
      else
        ERRORS=$((ERRORS + 1))
      fi
    done < <(find "$dashboard_dir" -name "*.json" -type f -print0 2>/dev/null)
    echo
  fi

  # Validate alerts
  if [[ -d "$target_dir/alerts" ]] || [[ "$target_dir" == *alerts* ]]; then
    local alert_dir="$target_dir"
    if [[ -d "$target_dir/alerts" ]]; then
      alert_dir="$target_dir/alerts"
    fi

    info "Validating alerts..."
    while IFS= read -r -d '' file; do
      # Skip _config.yaml
      if [[ "$(basename "$file")" == "_config.yaml" ]]; then
        continue
      fi

      if validate_alert "$file"; then
        success "$(basename "$file")"
        VALIDATED=$((VALIDATED + 1))
      else
        ERRORS=$((ERRORS + 1))
      fi
    done < <(find "$alert_dir" -name "*.yaml" -type f -print0 2>/dev/null)
    echo
  fi

  # Validate folders
  local folders_file="$GRAFANA_DIR/folders/folders.yaml"
  if [[ -f "$folders_file" ]] && [[ "$target_dir" == "$GRAFANA_DIR" || "$target_dir" == *folders* ]]; then
    info "Validating folders..."
    if validate_folders "$folders_file"; then
      success "folders.yaml"
      VALIDATED=$((VALIDATED + 1))
    else
      ERRORS=$((ERRORS + 1))
    fi
    echo
  fi

  # Summary
  echo "=================================="
  echo "Validation Summary"
  echo "=================================="
  echo "Files validated: $VALIDATED"
  echo "Errors: $ERRORS"
  echo "Warnings: $WARNINGS"
  echo

  # Exit code
  if [[ $ERRORS -gt 0 ]]; then
    error "Validation failed with $ERRORS error(s)"
    exit 1
  fi

  if [[ "$strict" == "true" ]] && [[ $WARNINGS -gt 0 ]]; then
    error "Validation failed with $WARNINGS warning(s) (strict mode)"
    exit 1
  fi

  success "Validation passed"
  exit 0
}

main "$@"
