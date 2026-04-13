#!/usr/bin/env bash
#
# Generate TypeScript + Python types for @datakinetic/dk-data-client from
# the live dk-data OpenAPI surfaces.
#
# Scrapes:
#   - PostgREST OpenAPI:    $DK_DATA_BASE_URL/            (served by PostgREST itself)
#   - FastAPI OpenAPI:      $DK_DATA_BASE_URL/openapi.json (served by data-platform router)
#
# Both are combined into a single schema fingerprint (sha256 over the
# stable-sorted merged JSON) that's baked into the client at build time.
# The version fingerprint check (src/version.ts) compares this against
# the server's self-reported fingerprint and warns on mismatch.
#
# Usage:
#   DK_DATA_BASE_URL=https://data.behaviorlabs.ai \
#   DK_DATA_API_KEY=dk_data_... \
#     ./scripts/generate-types.sh
#
# Environment:
#   DK_DATA_BASE_URL  Base URL of the metering proxy (required)
#   DK_DATA_API_KEY   API key for the scraping account (required)
#   OUTPUT_DIR        Where to drop the generated types (default: ./generated)
#
# Prerequisites:
#   - curl
#   - jq
#   - openapi-typescript (npm i -g openapi-typescript)
#   - datamodel-code-generator (pip install datamodel-code-generator)
#
# Exit codes:
#   0  success — types and fingerprint written
#   1  missing prerequisites
#   2  network / auth failure
#   3  type generation failed

set -euo pipefail

log() { printf '[generate-types] %s\n' "$*" >&2; }

: "${DK_DATA_BASE_URL:?DK_DATA_BASE_URL is required}"
: "${DK_DATA_API_KEY:?DK_DATA_API_KEY is required}"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/generated}"

# -----------------------------------------------------------------------------
# Prerequisite check
# -----------------------------------------------------------------------------

for cmd in curl jq openapi-typescript datamodel-codegen; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "missing prerequisite: $cmd"
        log "install: pnpm add -g openapi-typescript; pip install datamodel-code-generator"
        exit 1
    fi
done

mkdir -p "$OUTPUT_DIR/typescript" "$OUTPUT_DIR/python"

# -----------------------------------------------------------------------------
# Fetch PostgREST + FastAPI OpenAPI specs
# -----------------------------------------------------------------------------

log "fetching PostgREST OpenAPI from $DK_DATA_BASE_URL"
if ! curl -fsSL \
    -H "Authorization: Bearer $DK_DATA_API_KEY" \
    -H "Accept: application/openapi+json" \
    "$DK_DATA_BASE_URL/" > "$OUTPUT_DIR/postgrest.openapi.json"; then
    log "failed to fetch PostgREST OpenAPI"
    exit 2
fi

log "fetching FastAPI OpenAPI from $DK_DATA_BASE_URL/openapi.json"
if ! curl -fsSL \
    -H "Authorization: Bearer $DK_DATA_API_KEY" \
    "$DK_DATA_BASE_URL/openapi.json" > "$OUTPUT_DIR/fastapi.openapi.json"; then
    log "failed to fetch FastAPI OpenAPI"
    exit 2
fi

# -----------------------------------------------------------------------------
# Compute the combined schema fingerprint
# -----------------------------------------------------------------------------

log "computing combined schema fingerprint"
FINGERPRINT=$(
    jq -S -n --slurpfile pg "$OUTPUT_DIR/postgrest.openapi.json" \
             --slurpfile fa "$OUTPUT_DIR/fastapi.openapi.json" \
             '{ postgrest: $pg[0], fastapi: $fa[0] }' \
    | shasum -a 256 | awk '{print $1}'
)
log "fingerprint: $FINGERPRINT"

# -----------------------------------------------------------------------------
# Generate TypeScript types
# -----------------------------------------------------------------------------

log "generating TypeScript types"
openapi-typescript \
    "$OUTPUT_DIR/postgrest.openapi.json" \
    --output "$OUTPUT_DIR/typescript/postgrest.d.ts" \
    || { log "openapi-typescript failed for postgrest"; exit 3; }

openapi-typescript \
    "$OUTPUT_DIR/fastapi.openapi.json" \
    --output "$OUTPUT_DIR/typescript/fastapi.d.ts" \
    || { log "openapi-typescript failed for fastapi"; exit 3; }

# -----------------------------------------------------------------------------
# Generate Python types via datamodel-code-generator (Pydantic v2)
# -----------------------------------------------------------------------------

log "generating Python types"
datamodel-codegen \
    --input "$OUTPUT_DIR/postgrest.openapi.json" \
    --input-file-type openapi \
    --output "$OUTPUT_DIR/python/postgrest.py" \
    --output-model-type pydantic_v2.BaseModel \
    --use-standard-collections \
    --use-union-operator \
    || { log "datamodel-codegen failed for postgrest"; exit 3; }

datamodel-codegen \
    --input "$OUTPUT_DIR/fastapi.openapi.json" \
    --input-file-type openapi \
    --output "$OUTPUT_DIR/python/fastapi.py" \
    --output-model-type pydantic_v2.BaseModel \
    --use-standard-collections \
    --use-union-operator \
    || { log "datamodel-codegen failed for fastapi"; exit 3; }

# -----------------------------------------------------------------------------
# Bake the fingerprint into the client source (TS + Python)
# -----------------------------------------------------------------------------

log "baking fingerprint into client source"

# TS: update CLIENT_SCHEMA_FINGERPRINT in src/version.ts
TS_VERSION_FILE="$(pwd)/typescript/src/version.ts"
if [[ -f "$TS_VERSION_FILE" ]]; then
    # macOS / Linux sed compatibility dance
    if sed --version >/dev/null 2>&1; then
        sed -i -E "s#^export const CLIENT_SCHEMA_FINGERPRINT = \".*\";#export const CLIENT_SCHEMA_FINGERPRINT = \"$FINGERPRINT\";#" "$TS_VERSION_FILE"
    else
        sed -i '' -E "s#^export const CLIENT_SCHEMA_FINGERPRINT = \".*\";#export const CLIENT_SCHEMA_FINGERPRINT = \"$FINGERPRINT\";#" "$TS_VERSION_FILE"
    fi
fi

# Python: write the fingerprint into a dedicated generated module
PY_FINGERPRINT_FILE="$(pwd)/python/dk_data_client/_fingerprint.py"
cat > "$PY_FINGERPRINT_FILE" <<EOF
# Auto-generated by scripts/generate-types.sh — DO NOT EDIT BY HAND.
# The fingerprint is regenerated on every type-gen run against the
# live dk-data OpenAPI surfaces. Used by the server-info schema check
# (see version.py). Warn-only; does not throw on mismatch.
CLIENT_SCHEMA_FINGERPRINT = "$FINGERPRINT"
EOF

log "done"
log "outputs: $OUTPUT_DIR/{typescript,python}"
log "fingerprint: $FINGERPRINT"
