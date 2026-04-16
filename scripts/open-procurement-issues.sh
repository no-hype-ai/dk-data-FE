#!/usr/bin/env bash
# Open GitHub issues for every T4 licensed data source that needs procurement approval.
# Idempotent: skips if an open issue with the same title already exists.
# Plan reference: plan.md §B.11.
set -eu

REPO="data-kinetic/dk-data-FE"

# name|domain|use_case|vendor|cost_tier|alternatives
SOURCES=(
  "AHA Annual Survey|hcs|Hospital-level org structure, service lines, bed counts, network membership|American Hospital Association|~5-digit annual subscription|CMS Hospital General Info + PECOS cover basic org data at T1"
  "HCUP NIS|hcs|National Inpatient Sample — utilization, cost, outcomes at national scale|AHRQ (HCUP)|Data Use Agreement, research fee per release|CMS Inpatient PUF (T1) has provider-level summaries but no patient-level sampling"
  "HCUP NEDS|hcs|National Emergency Department Sample|AHRQ (HCUP)|Data Use Agreement, research fee per release|No public ED utilization substitute"
  "IQVIA MIDAS sample|mol|Global drug sales volume and pricing across markets|IQVIA|commercial|WHO GHED + OECD health (T1) cover aggregate national spend; country-specific formularies (T1/T3) for per-drug"
  "Scopus|hcp|Publication and citation index for researcher / KOL analytics|Elsevier|commercial|OpenAlex (T1) + Crossref (T1) + EuropePMC (T1) cover most use cases"
  "Dimensions|hcp|Research intelligence (grants + pubs + clinical trials linked)|Digital Science|commercial (free academic tier possible)|OpenAlex + NIH RePORTER + ClinicalTrials.gov (all T1/T2) cover the primary signals"
  "HIMSS Analytics|hcs|Hospital digital-maturity (EMRAM stage) and IT spend benchmarking|HIMSS|commercial|No public substitute for EMRAM"
  "ACS TQIP|hcs|Trauma Quality Improvement Program registry|American College of Surgeons|participant institution only|No public substitute"
  "STS National Database|hcs|Cardiothoracic surgery quality registry|Society of Thoracic Surgeons|participant institution only|CMS inpatient / provider quality reports (T1) as rough proxy"
)

DECISION_MAKER="@nick  <!-- replace with actual procurement decision-maker -->"

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r name domain use_case vendor cost_tier alternatives <<< "$entry"

  title="feat(source): onboard ${name} (T4 — procurement required)"

  # Idempotency: check if an open issue with the same title already exists
  existing=$(gh issue list --repo "$REPO" --state open --search "${title} in:title" --json number --jq '.[0].number' 2>/dev/null || true)
  if [ -n "$existing" ] && [ "$existing" != "null" ]; then
    echo "SKIP (#$existing exists): $title"
    continue
  fi

  body=$(cat <<EOF
## Data use case
${use_case}

## Vendor / licensor
${vendor}

## Cost tier
${cost_tier}

## Decision-maker
${DECISION_MAKER}

## Accessible alternatives (T1 / T2) that partially cover the need
${alternatives}

## Procurement state machine
- [ ] \`procurement:pending\` — this issue is open; decision-maker reviewing
- [ ] \`procurement:approved\` → engineering ticket unblocked; move label, open the onboarding fetcher
- [ ] \`procurement:blocked\` → document which alternative(s) are being used instead; close with reason

## Reference
- plan.md §B.11 (procurement workflow)
- plan.md §E.3 (source inventory)
EOF
)

  url=$(gh issue create \
    --repo "$REPO" \
    --title "$title" \
    --label "source:stub,tier:T4,procurement:pending,domain:${domain}" \
    --body "$body" 2>&1 | tail -1)
  echo "CREATED: $url  ($name)"
done
