#!/usr/bin/env bash
# Bootstrap the dk-data-FE source/hydrate label taxonomy across dk-data-FE and dk-cli.
# Idempotent: swallows "label already exists" errors from gh label create.
# Plan reference: plan.md §B.9.
set -u

REPOS=(data-kinetic/dk-data-FE data-kinetic/dk-cli)

# label|color|description
LABELS=(
  "source:stub|e4e669|Source entry exists but fetcher is not yet implemented"
  "source:fetcher_ready|fbca04|Fetcher implemented, not yet live in hydration"
  "source:live|0e8a16|Source fully live in hydration pipeline"
  "domain:mol|5319e7|Molecule / drug / compound domain"
  "domain:hcs|1d76db|Healthcare services / CMS / provider domain"
  "domain:hcp|0052cc|Healthcare professional / researcher / KOL domain"
  "domain:ind|006b75|Indication / disease / epidemiology domain"
  "domain:ip|bfd4f2|Intellectual property / patents / trademarks domain"
  "domain:dev|b60205|Medical devices domain (new)"
  "tier:T1|0e8a16|Free & easy — open data, no registration"
  "tier:T2|fbca04|Free with registration / free API key"
  "tier:T3|ff9f1c|Accessible via scraping (public web)"
  "tier:T4|d93f0b|Licensed / commercial / paywalled"
  "priority:top15|d73a4a|One of the 15 first onboardings"
  "procurement:pending|fbca04|Licensed source — procurement approval pending"
  "procurement:approved|0e8a16|Licensed source — procurement approved"
  "procurement:blocked|b60205|Licensed source — procurement blocked"
  "area:hydrate|c5def5|Hydration / ingestion path"
  "area:data|c5def5|Data API / keys / schemas"
  "area:observability|c5def5|Grafana / alerts / metrics / logs"
  "scope:immediate|d93f0b|Horizon 1 — next hydration window"
  "scope:near-term|fbca04|Horizon 2 — 1–4 weeks"
  "scope:scale-ready|0e8a16|Horizon 3 — 4–12 weeks"
)

created=0
skipped=0
failed=0

for repo in "${REPOS[@]}"; do
  echo "==> $repo"
  for entry in "${LABELS[@]}"; do
    IFS='|' read -r name color desc <<< "$entry"
    if gh label create "$name" --repo "$repo" --color "$color" --description "$desc" 2>&1 | grep -q "already exists"; then
      skipped=$((skipped+1))
      printf "  - %s (exists)\n" "$name"
    elif gh label create "$name" --repo "$repo" --color "$color" --description "$desc" --force >/dev/null 2>&1; then
      created=$((created+1))
      printf "  + %s\n" "$name"
    else
      failed=$((failed+1))
      printf "  ! %s (failed)\n" "$name"
    fi
  done
done

echo
echo "Summary: created=$created skipped=$skipped failed=$failed"
