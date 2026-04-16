#!/usr/bin/env bash
# grafana-api.sh - Shared functions for Grafana API operations
# Vendored from dk-alchemy:grafana/scripts/lib/grafana-api.sh (plan.md §J.2 step 1).
# Source this file at the start of each script.

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

# Grafana API base URL
GRAFANA_URL="${GRAFANA_URL:-https://grafana.behaviorlabs.ai}"

# API key from environment or Doppler
GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"

# Retry settings
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-5}"

# ============================================================================
# Color Output
# ============================================================================

if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  BOLD='\033[1m'
  NC='\033[0m' # No Color
else
  RED='' GREEN='' YELLOW='' BLUE='' BOLD='' NC=''
fi

# ============================================================================
# Output Functions
# ============================================================================

info() {
  echo -e "${BLUE}[INFO]${NC} $*"
}

success() {
  echo -e "${GREEN}[OK]${NC} $*"
}

warn() {
  echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

debug() {
  if [[ "${DEBUG:-false}" == "true" ]]; then
    echo -e "${YELLOW}[DEBUG]${NC} $*" >&2
  fi
}

# ============================================================================
# Dependency Checks
# ============================================================================

check_dependencies() {
  local missing=()

  if ! command -v curl &>/dev/null; then
    missing+=("curl")
  fi

  if ! command -v jq &>/dev/null; then
    missing+=("jq")
  fi

  if ! command -v yq &>/dev/null; then
    missing+=("yq")
  fi

  if [[ ${#missing[@]} -gt 0 ]]; then
    error "Missing dependencies: ${missing[*]}"
    error "Install with: brew install ${missing[*]}"
    return 1
  fi
}

# ============================================================================
# Authentication
# ============================================================================

# Get API key from environment or Doppler
get_api_key() {
  if [[ -n "$GRAFANA_API_KEY" ]]; then
    echo "$GRAFANA_API_KEY"
    return 0
  fi

  # Try Doppler if available
  if command -v doppler &>/dev/null; then
    local key
    key=$(doppler secrets get GRAFANA_API_KEY --plain 2>/dev/null || true)
    if [[ -n "$key" ]]; then
      echo "$key"
      return 0
    fi
  fi

  error "GRAFANA_API_KEY not set and Doppler not available"
  return 1
}

# Build authorization header
get_auth_header() {
  local key
  key=$(get_api_key) || return 1
  echo "Authorization: Bearer $key"
}

# ============================================================================
# HTTP Request Wrapper
# ============================================================================

# Make HTTP request with retry logic
# Usage: grafana_request METHOD ENDPOINT [DATA]
grafana_request() {
  local method="$1"
  local endpoint="$2"
  local data="${3:-}"

  local url="${GRAFANA_URL}${endpoint}"
  local auth_header
  auth_header=$(get_auth_header) || return 1

  local attempt=1
  local response
  local http_code

  while [[ $attempt -le $MAX_RETRIES ]]; do
    debug "Request attempt $attempt: $method $url"

    local curl_args=(
      -s
      -w "\n%{http_code}"
      -H "$auth_header"
      -H "Content-Type: application/json"
      -X "$method"
    )

    if [[ -n "$data" ]]; then
      curl_args+=(-d "$data")
    fi

    curl_args+=("$url")

    # Execute request
    response=$(curl "${curl_args[@]}" 2>/dev/null) || {
      warn "Request failed (attempt $attempt/$MAX_RETRIES)"
      ((attempt++))
      sleep "$RETRY_DELAY"
      continue
    }

    # Extract HTTP code from last line
    http_code=$(echo "$response" | tail -1)
    response=$(echo "$response" | sed '$d')

    debug "HTTP $http_code: $response"

    case "$http_code" in
      2*)
        echo "$response"
        return 0
        ;;
      401)
        error "Unauthorized - check GRAFANA_API_KEY"
        return 1
        ;;
      403)
        error "Forbidden - insufficient permissions"
        return 1
        ;;
      404)
        # Not always an error, caller should handle
        echo "$response"
        return 44  # Special return code for 404
        ;;
      409)
        # Conflict - resource exists
        echo "$response"
        return 9  # Special return code for conflict
        ;;
      429)
        warn "Rate limited, waiting..."
        sleep $((RETRY_DELAY * 2))
        ((attempt++))
        continue
        ;;
      5*)
        warn "Server error $http_code (attempt $attempt/$MAX_RETRIES)"
        ((attempt++))
        sleep "$RETRY_DELAY"
        continue
        ;;
      *)
        error "Unexpected response: HTTP $http_code"
        echo "$response" >&2
        return 1
        ;;
    esac
  done

  error "Max retries exceeded"
  return 1
}

# ============================================================================
# Folder Operations
# ============================================================================

# List all folders
# Returns: JSON array of folders
list_folders() {
  grafana_request GET "/api/folders"
}

# Get folder by UID
# Usage: get_folder <uid>
get_folder() {
  local uid="$1"
  grafana_request GET "/api/folders/$uid"
}

# Create folder
# Usage: create_folder <uid> <title>
create_folder() {
  local uid="$1"
  local title="$2"

  local data
  data=$(jq -n \
    --arg uid "$uid" \
    --arg title "$title" \
    '{uid: $uid, title: $title}'
  )

  local result
  local ret=0
  result=$(grafana_request POST "/api/folders" "$data") || ret=$?

  if [[ $ret -eq 9 ]]; then
    # Folder already exists, this is OK
    debug "Folder '$uid' already exists"
    get_folder "$uid"
    return 0
  elif [[ $ret -ne 0 ]]; then
    return $ret
  fi

  echo "$result"
}

# Update folder title
# Usage: update_folder <uid> <title>
update_folder() {
  local uid="$1"
  local title="$2"

  # Get current version
  local current
  current=$(get_folder "$uid") || return 1
  local version
  version=$(echo "$current" | jq -r '.version')

  local data
  data=$(jq -n \
    --arg title "$title" \
    --argjson version "$version" \
    '{title: $title, version: $version}'
  )

  grafana_request PUT "/api/folders/$uid" "$data"
}

# Sync folder from definition
# Usage: sync_folder <uid> <title>
sync_folder() {
  local uid="$1"
  local title="$2"

  local existing
  local ret=0
  existing=$(get_folder "$uid") || ret=$?

  if [[ $ret -eq 44 ]]; then
    # Folder doesn't exist, create it
    info "Creating folder: $title ($uid)"
    create_folder "$uid" "$title"
  elif [[ $ret -ne 0 ]]; then
    return $ret
  else
    # Folder exists, check if title needs update
    local current_title
    current_title=$(echo "$existing" | jq -r '.title')
    if [[ "$current_title" != "$title" ]]; then
      info "Updating folder title: $current_title -> $title"
      update_folder "$uid" "$title"
    else
      debug "Folder '$uid' is up to date"
    fi
  fi
}

# ============================================================================
# Dashboard Operations
# ============================================================================

# Get dashboard by UID
# Usage: get_dashboard <uid>
# Returns: Full dashboard response with meta and dashboard
get_dashboard() {
  local uid="$1"
  grafana_request GET "/api/dashboards/uid/$uid"
}

# Search dashboards
# Usage: search_dashboards [type] [folder_id] [query]
search_dashboards() {
  local type="${1:-dash-db}"
  local folder_id="${2:-}"
  local query="${3:-}"

  local endpoint="/api/search?type=$type"

  if [[ -n "$folder_id" ]]; then
    endpoint="${endpoint}&folderIds=$folder_id"
  fi

  if [[ -n "$query" ]]; then
    endpoint="${endpoint}&query=$(echo "$query" | jq -sRr @uri)"
  fi

  grafana_request GET "$endpoint"
}

# Upsert dashboard (create or update)
# Usage: upsert_dashboard <json_file> [folder_uid] [message]
upsert_dashboard() {
  local json_file="$1"
  local folder_uid="${2:-}"
  local message="${3:-Synced via GitOps}"

  if [[ ! -f "$json_file" ]]; then
    error "File not found: $json_file"
    return 1
  fi

  # Read and prepare dashboard JSON
  local dashboard_json
  dashboard_json=$(cat "$json_file")

  # Check if it has __metadata wrapper
  if echo "$dashboard_json" | jq -e '.__metadata' &>/dev/null; then
    # Extract folder from metadata if not provided
    if [[ -z "$folder_uid" ]]; then
      folder_uid=$(echo "$dashboard_json" | jq -r '.__metadata.folder // empty' | tr '[:upper:]' '[:lower:]')
    fi
    # Extract actual dashboard
    dashboard_json=$(echo "$dashboard_json" | jq '.dashboard')
  fi

  # Remove version and id for upsert (let Grafana manage these)
  dashboard_json=$(echo "$dashboard_json" | jq 'del(.version, .id)')

  # Build request body
  local data
  data=$(jq -n \
    --argjson dashboard "$dashboard_json" \
    --arg folderUid "$folder_uid" \
    --arg message "$message" \
    '{
      dashboard: $dashboard,
      folderUid: $folderUid,
      overwrite: true,
      message: $message
    }'
  )

  grafana_request POST "/api/dashboards/db" "$data"
}

# Delete dashboard by UID
# Usage: delete_dashboard <uid>
delete_dashboard() {
  local uid="$1"
  grafana_request DELETE "/api/dashboards/uid/$uid"
}

# ============================================================================
# Alert Rule Operations (Provisioning API)
# ============================================================================

# List all alert rules
# Usage: list_alert_rules
list_alert_rules() {
  grafana_request GET "/api/v1/provisioning/alert-rules"
}

# Get alert rule by UID
# Usage: get_alert_rule <uid>
get_alert_rule() {
  local uid="$1"
  grafana_request GET "/api/v1/provisioning/alert-rules/$uid"
}

# Create or update alert rule
# Usage: upsert_alert_rule <rule_json>
upsert_alert_rule() {
  local rule_json="$1"
  local uid
  uid=$(echo "$rule_json" | jq -r '.uid')

  # Check if rule exists
  local existing
  local ret=0
  existing=$(get_alert_rule "$uid" 2>/dev/null) || ret=$?

  if [[ $ret -eq 44 ]]; then
    # Rule doesn't exist, create it
    debug "Creating alert rule: $uid"
    grafana_request POST "/api/v1/provisioning/alert-rules" "$rule_json"
  else
    # Rule exists, update it
    debug "Updating alert rule: $uid"
    grafana_request PUT "/api/v1/provisioning/alert-rules/$uid" "$rule_json"
  fi
}

# Delete alert rule by UID
# Usage: delete_alert_rule <uid>
delete_alert_rule() {
  local uid="$1"
  grafana_request DELETE "/api/v1/provisioning/alert-rules/$uid"
}

# Legacy function for compatibility
# Usage: upsert_alert_rules <namespace> <rules_json>
upsert_alert_rules() {
  local namespace="$1"
  local rules_json="$2"
  warn "upsert_alert_rules is deprecated, use upsert_alert_rule instead"
  # This function is kept for backward compatibility but should not be used
  return 1
}

# ============================================================================
# JSON Parsing Helpers
# ============================================================================

# Extract UID from dashboard JSON
# Usage: extract_uid <json_file>
extract_uid() {
  local file="$1"
  if jq -e '.__metadata' "$file" &>/dev/null; then
    jq -r '.dashboard.uid' "$file"
  else
    jq -r '.uid' "$file"
  fi
}

# Extract title from dashboard JSON
# Usage: extract_title <json_file>
extract_title() {
  local file="$1"
  if jq -e '.__metadata' "$file" &>/dev/null; then
    jq -r '.dashboard.title' "$file"
  else
    jq -r '.title' "$file"
  fi
}

# Extract folder from metadata
# Usage: extract_folder <json_file>
extract_folder() {
  local file="$1"
  jq -r '.__metadata.folder // empty' "$file" | tr '[:upper:]' '[:lower:]'
}

# ============================================================================
# Initialization
# ============================================================================

# Verify API connectivity
verify_connection() {
  info "Verifying Grafana API connectivity..."
  local result
  if result=$(grafana_request GET "/api/health" 2>/dev/null); then
    if echo "$result" | jq -e '.database == "ok"' &>/dev/null; then
      success "Connected to Grafana at $GRAFANA_URL"
      return 0
    fi
  fi
  error "Cannot connect to Grafana at $GRAFANA_URL"
  return 1
}

# Initialize - check deps and verify connection
init_grafana_api() {
  check_dependencies || return 1
  verify_connection || return 1
}
