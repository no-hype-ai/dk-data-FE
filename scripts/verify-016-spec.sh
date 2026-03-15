#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# Spec §11 Verification Script — 016-cms-puf-datasource-integration
# Covers: T114 (verification commands), T115 (canon checklist),
#         T116 (load test note), T117 (agent cost note), T118 (PostgREST gold)
# ────────────────────────────────────────────────────────────────────
set -uo pipefail
# Note: -e intentionally omitted — grep returning 0 matches exits 1, which is expected

GREEN='\033[92m'
RED='\033[91m'
YELLOW='\033[93m'
NC='\033[0m'
PASS="${GREEN}✓${NC}"
FAIL="${RED}✗${NC}"
WARN="${YELLOW}⚠${NC}"

TOTAL=0
PASSED=0
FAILED=0
WARNINGS=0

check() {
    TOTAL=$((TOTAL + 1))
    local name="$1"
    local result="$2"
    local detail="${3:-}"
    if [ "$result" = "pass" ]; then
        PASSED=$((PASSED + 1))
        echo -e "  ${PASS} ${name}${detail:+  —  ${detail}}"
    elif [ "$result" = "warn" ]; then
        WARNINGS=$((WARNINGS + 1))
        echo -e "  ${WARN} ${name}${detail:+  —  ${detail}}"
    else
        FAILED=$((FAILED + 1))
        echo -e "  ${FAIL} ${name}${detail:+  —  ${detail}}"
    fi
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " 016-cms-puf-datasource-integration — Spec Verification"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════"

# ── §11.1: Codebase Checks ──────────────────────────────────────────
echo ""
echo "━━━ 1. Codebase Structure ━━━"

# Fetchers (expect 30+)
FETCHER_COUNT=$(find src/dk_data/ingestion/fetchers -name 'cms_*.py' | wc -l | tr -d ' ')
[ "$FETCHER_COUNT" -ge 28 ] && check "CMS fetchers" "pass" "${FETCHER_COUNT} files" \
                              || check "CMS fetchers" "fail" "expected ≥28, got ${FETCHER_COUNT}"

# Source loaders (expect 30+)
LOADER_COUNT=$(find src/dk_data/ingestion/sources -name 'cms_*.py' | wc -l | tr -d ' ')
[ "$LOADER_COUNT" -ge 28 ] && check "CMS source loaders" "pass" "${LOADER_COUNT} files" \
                             || check "CMS source loaders" "fail" "expected ≥28, got ${LOADER_COUNT}"

# SQLMesh bronze models
BRONZE_COUNT=$(find src/dk_data/sqlmesh/models/cms/bronze -name '*.sql' 2>/dev/null | wc -l | tr -d ' ')
[ "$BRONZE_COUNT" -ge 24 ] && check "Bronze SQLMesh models" "pass" "${BRONZE_COUNT} files" \
                             || check "Bronze SQLMesh models" "fail" "expected ≥24, got ${BRONZE_COUNT}"

# SQLMesh silver models
SILVER_COUNT=$(find src/dk_data/sqlmesh/models/cms/silver -name '*.sql' 2>/dev/null | wc -l | tr -d ' ')
[ "$SILVER_COUNT" -ge 3 ] && check "Silver SQLMesh models" "pass" "${SILVER_COUNT} files" \
                            || check "Silver SQLMesh models" "fail" "expected ≥3, got ${SILVER_COUNT}"

# SQLMesh gold models
GOLD_COUNT=$(find src/dk_data/sqlmesh/models/cms/gold -name '*.sql' 2>/dev/null | wc -l | tr -d ' ')
[ "$GOLD_COUNT" -ge 4 ] && check "Gold SQLMesh models" "pass" "${GOLD_COUNT} files" \
                          || check "Gold SQLMesh models" "fail" "expected ≥4, got ${GOLD_COUNT}"

# Agents (expect 6 + base)
AGENT_COUNT=$(find src/dk_data/agents -name '*.py' ! -name '__init__.py' ! -name 'base_agent.py' | wc -l | tr -d ' ')
[ "$AGENT_COUNT" -ge 6 ] && check "CMS agents" "pass" "${AGENT_COUNT} agents" \
                           || check "CMS agents" "fail" "expected ≥6, got ${AGENT_COUNT}"

# Migrations
MIGRATION_COUNT=$(find src/dk_data/sql/migrations -name '08[3-8]_cms_*.sql' | wc -l | tr -d ' ')
[ "$MIGRATION_COUNT" -ge 6 ] && check "CMS migrations (083–088)" "pass" "${MIGRATION_COUNT} files" \
                               || check "CMS migrations (083–088)" "fail" "expected 6, got ${MIGRATION_COUNT}"

# ── §11.2: K8s Manifests ────────────────────────────────────────────
echo ""
echo "━━━ 2. Kubernetes Manifests ━━━"

# CMS CronJobs (expect 28)
CRONJOB_COUNT=$(find k8s/base/ingestion -name 'cronjob-fetch-cms-*.yaml' | wc -l | tr -d ' ')
[ "$CRONJOB_COUNT" -ge 28 ] && check "CMS CronJob manifests" "pass" "${CRONJOB_COUNT} files" \
                              || check "CMS CronJob manifests" "fail" "expected ≥28, got ${CRONJOB_COUNT}"

# Agent CronJob
[ -f k8s/base/ingestion/cronjob-agents-monthly.yaml ] && check "Agent monthly CronJob" "pass" \
                                                        || check "Agent monthly CronJob" "fail"

# Job template
[ -f k8s/base/ingestion/job-agent-template.yaml ] && check "Agent job template" "pass" \
                                                    || check "Agent job template" "fail"

# Gold refresh CronJob
[ -f k8s/base/ingestion/cronjob-cms-gold-refresh.yaml ] && check "Gold refresh CronJob" "pass" \
                                                          || check "Gold refresh CronJob" "fail"

# Grafana dashboard ConfigMap
[ -f k8s/base/grafana-cms-dashboard.yaml ] && check "Grafana dashboard ConfigMap" "pass" \
                                            || check "Grafana dashboard ConfigMap" "fail"

# USP seed job
[ -f k8s/base/job-usp-seed.yaml ] && check "USP seed job" "pass" \
                                    || check "USP seed job" "fail"

# ── §10: Canon Compliance ───────────────────────────────────────────
echo ""
echo "━━━ 3. Canon Compliance (§10) ━━━"

# No :latest tags in K8s
LATEST_COUNT=$(grep -r ':latest' k8s/ --include='*.yaml' 2>/dev/null | grep -v '__pycache__' | wc -l | tr -d ' ')
[ "$LATEST_COUNT" -eq 0 ] && check "No :latest tags in K8s" "pass" \
                            || check "No :latest tags in K8s" "fail" "${LATEST_COUNT} occurrences"

# No MCP routes remain
MCP_COUNT=$(grep -r 'mcp' src/dk_data/api/routes/ --include='*.py' 2>/dev/null | grep -v '__pycache__' | wc -l | tr -d ' ')
[ "$MCP_COUNT" -eq 0 ] && check "No MCP routes remain" "pass" \
                         || check "No MCP routes remain" "fail" "${MCP_COUNT} references"

# No direct anthropic imports in agents
ANTHROPIC_COUNT=$(grep -r 'import anthropic' src/dk_data/agents/ --include='*.py' 2>/dev/null | wc -l | tr -d ' ')
[ "$ANTHROPIC_COUNT" -eq 0 ] && check "No direct anthropic SDK in agents" "pass" \
                               || check "No direct anthropic SDK in agents" "fail" "${ANTHROPIC_COUNT} imports"

# Doppler secret manifest exists
[ -f k8s/base/doppler-secret.yaml ] && check "Doppler secret manifest" "pass" \
                                      || check "Doppler secret manifest" "fail"

# PostgREST gold schema configured
if grep -q 'gold' k8s/base/postgrest/configmap.yaml 2>/dev/null; then
    check "PostgREST gold schema in config" "pass"
else
    check "PostgREST gold schema in config" "fail"
fi

# Dollar-quoting in CMS SQL
if grep -q '\$cms\$' src/dk_data/sql/migrations/083_cms_raw_tables.sql 2>/dev/null; then
    check "Dollar-quoting (\$cms\$) in SQL" "pass"
else
    check "Dollar-quoting (\$cms\$) in SQL" "warn" "check manually"
fi

# ── §11.3: Data & Deployment ────────────────────────────────────────
echo ""
echo "━━━ 4. Data Assets & Deployment ━━━"

# USP alignment file
[ -f data/usp/usp_mmg_v9_alignment.xlsx ] && check "USP alignment file in repo" "pass" \
                                            || check "USP alignment file in repo" "fail"

# Git LFS tracking
if grep -q 'data/usp' .gitattributes 2>/dev/null; then
    check "USP file tracked by Git LFS" "pass"
else
    check "USP file tracked by Git LFS" "fail"
fi

# Dockerfile copies USP data
if grep -q 'data/usp' Dockerfile 2>/dev/null; then
    check "Dockerfile copies USP data" "pass"
else
    check "Dockerfile copies USP data" "fail"
fi

# DrugBank seed data
[ -d data/drugbank ] && check "DrugBank seed data directory" "pass" \
                       || check "DrugBank seed data directory" "warn" "may be in Git LFS"

# ── §11.4: Test Coverage ────────────────────────────────────────────
echo ""
echo "━━━ 5. Test Files ━━━"

for testfile in \
    tests/test_integration_cms_puf.py \
    tests/test_integration_nppes_pipeline.py \
    tests/test_integration_agent_pipeline.py \
    tests/test_cms_provider_fetchers.py \
    tests/test_cms_provider_loaders.py \
    tests/test_cms_facility_fetchers.py \
    tests/test_cms_facility_loaders.py \
    tests/test_agents/test_service_line_inference.py \
    tests/test_agents/test_contact_verification.py \
    tests/test_postgrest_gold_cms.py; do
    if [ -f "$testfile" ]; then
        check "$(basename $testfile)" "pass"
    else
        check "$(basename $testfile)" "fail" "missing"
    fi
done

# ── §11.5: Linting ──────────────────────────────────────────────────
echo ""
echo "━━━ 6. Linting ━━━"

if command -v ruff &>/dev/null; then
    LINT_ERRORS=$(ruff check src/dk_data/agents/ src/dk_data/ingestion/fetchers/cms_*.py src/dk_data/ingestion/sources/cms_*.py 2>&1 | grep -c 'error' || true)
    [ "$LINT_ERRORS" -eq 0 ] && check "ruff check (agents + CMS fetchers/loaders)" "pass" \
                               || check "ruff check (agents + CMS fetchers/loaders)" "warn" "${LINT_ERRORS} issues"
else
    check "ruff check" "warn" "ruff not installed"
fi

# ── §11.6: Notes for Manual Verification ─────────────────────────────
echo ""
echo "━━━ 7. Manual Verification Notes ━━━"
echo "  T010: LITELLM_BASE_URL and LITELLM_API_KEY must be added to Doppler"
echo "        project 'dk-data-fe' for both stg and prd configs."
echo "        K8s manifests already reference these via dk-data-secrets."
echo ""
echo "  T116: NPPES load test (8GB ingest < 2 hours) — run in staging:"
echo "        kubectl create job nppes-loadtest-\$(date +%s) \\"
echo "          --from=cronjob/fetch-cms-nppes -n dk-data-prod"
echo ""
echo "  T117: Agent cost validation (\$175–\$385/month) — check after first"
echo "        monthly agent run via: SELECT SUM(estimated_cost_usd)"
echo "        FROM meta.agent_execution_log WHERE started_at > now() - interval '30d';"
echo ""
echo "  T118: PostgREST gold views — verify in staging:"
echo "        curl -s https://data.preview.behaviorlabs.ai/cms_provider_360?limit=1"
echo "        curl -s https://data.preview.behaviorlabs.ai/cms_facility_360?limit=1"
echo "        curl -s https://data.preview.behaviorlabs.ai/cms_drug_market_profile?limit=1"
echo "        curl -s https://data.preview.behaviorlabs.ai/cms_market_analytics?limit=1"
echo "        curl -s https://data.preview.behaviorlabs.ai/cms_provider_network?limit=1"

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e " Results: ${GREEN}${PASSED}${NC} passed, ${RED}${FAILED}${NC} failed, ${YELLOW}${WARNINGS}${NC} warnings (${TOTAL} total)"
echo "═══════════════════════════════════════════════════════════════"

[ "$FAILED" -eq 0 ] && exit 0 || exit 1
