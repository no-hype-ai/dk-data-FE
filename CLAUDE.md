# /Users/pschloz/Desktop/DataKinetic/dk-data-FE

This project uses [dk](https://github.com/tumeke-stealth/tumeke-tools) for spec-driven development.

## DK Commands

Available commands (invoke as slash commands in your AI tool):

- `/dk.constitution` — Establish project context and conventions
- `/dk.specify` — Generate feature specification from a brief
- `/dk.clarify` — Resolve ambiguities in specifications
- `/dk.plan` — Create technical implementation plan
- `/dk.tasks` — Generate dependency-ordered task breakdown
- `/dk.implement` — Execute implementation tasks
- `/dk.analyze` — Cross-artifact consistency audit
- `/dk.checklist` — Pre-merge verification checklist
- `/dk.taskstoissues` — Convert tasks to GitHub issues
- `/dk.auto` — Autonomous pipeline (specify -> plan -> tasks -> analyze)
- `/dk.debug` — End-to-end app audit with Chrome DevTools
- `/dk.swarm` — Parallel implementation via git worktrees

## Project Structure

- `.dk/` — DK configuration and artifacts
- `.dk/config.yaml` — Project configuration
- `.dk/memory/` — Persistent project memory (constitution, etc.)
- `.dk/specs/` — Feature specifications and plans
- `.dk/scripts/` — Helper scripts

## Principles

This project honors `.dk/memory/principles.md` — read it before starting any task.
The bar is: **simple, complete, senior**. Plan before code (3+ steps), verify before done.

## AI Agents

Configured for: claude

## Active PostgreSQL Schemas

### Domain schemas (always use the domain prefix)

- `mol_raw`, `mol_bronze`, `mol_silver`, `mol_gold`, `mol_api` — Molecule / drug / compound data
- `hcs_raw`, `hcs_bronze`, `hcs_silver`, `hcs_gold` — Healthcare system / CMS / provider data
- `ind_raw`, `ind_bronze`, `ind_silver`, `ind_gold` — Indication / disease / epidemiology data
- `hcp_silver`, `hcp_gold` — Healthcare professional / KOL / researcher data
- `ip_raw`, `ip_bronze`, `ip_silver`, `ip_gold`, `ip_api` — Intellectual property / patents / trademarks / designs
- `dev_raw`, `dev_bronze`, `dev_silver`, `dev_gold` — Medical devices (FDA 510(k), PMA, classification, UDI)

**Rule**: every new table, view, function, or materialized view lives in a domain-prefixed schema. If you find yourself wanting to put something in `api`, `public`, or an unprefixed name, stop and pick the right domain first.

### Unprefixed-schema carve-outs (do NOT add domain data here)

These schemas exist for cross-domain infrastructure and are the *only* exceptions to the domain-prefix rule:

| Schema | Purpose | What belongs here |
|---|---|---|
| `meta` | Job orchestration | `job_locks`, `backfill_state`, `refresh_state`, `transform_runs`, `model_lineage` |
| `staging` | Transient bronze→silver staging | Throwaway tables produced by ingestion pipelines |
| `mart` | Cross-domain marts | Anything that joins 2+ domains (rare — prefer domain `_gold`) |
| `scoring` | Cross-domain scoring models | ML-model-output tables that span domains |
| `targeting` | Targeting workflows | Target-list-builder outputs |
| `xenon` | Xenon service internals | Internal to the xenon service |
| `application` | App-level state | Session, feature flag, app-config state |
| `api` | PostgREST public surface | **Deprecated** — use domain-prefixed schemas instead. The only views that may stay in `api` are ones PostgREST explicitly publishes and that touch multiple domains |

**When in doubt**: put it in a domain schema and ask during review. Unprefixed carve-outs are a one-way door — once something lands in `mart` or `xenon` it's expensive to relocate.

### Agents schema collision (US-18)

There are three `*agents*` schemas in production and only one of them is where agents actually live:

| Schema | Status | Contents |
|---|---|---|
| `agents` | **Canonical** | Agent registrations, agent state, agent chat history |
| `mol_agents` | Deprecated | Empty or stub tables left from an earlier naming pass — do not add to |
| `hcs_agents` | Deprecated | Same — empty stubs |

New agent data goes into `agents`. If you find yourself writing `mol_agents.something`, you have the wrong schema — switch to `agents`. Migration 221 (US-18 T132) consolidates `mol_agents` and `hcs_agents` into `agents` and drops the empty stubs.

## Silver Hub Architecture (feature/001-silver-medallion-rebuild)

The silver layer is built on **12 canonical entity-resolution hubs**:

| Hub | Schema | Key Tables |
|-----|--------|-----------|
| Molecule | `mol_silver` | `molecules`, `molecule_identifiers`, `molecule_names` |
| Drug Product | `mol_silver` | `drug_products`, `drug_product_identifiers`, `drug_product_names`, `drug_product_ingredients` |
| Company | `mol_silver` | `companies`, `company_identifiers`, `company_names` |
| Target | `mol_silver` | `targets`, `target_identifiers`, `target_names`, `target_sequences` |
| Provider | `hcs_silver` | `providers`, `provider_identifiers`, `provider_names` |
| Facility | `hcs_silver` | `facilities`, `facility_identifiers`, `facility_names` |
| Condition | `ind_silver` | `conditions`, `condition_identifiers`, `condition_names` |
| Researcher | `hcp_silver` | `researchers`, `researcher_identifiers`, `researcher_names` |
| Patent | `ip_silver` | `patents`, `patent_identifiers`, `patent_names` |
| Trademark | `ip_silver` | `trademarks`, `trademark_identifiers`, `trademark_names` |
| Design | `ip_silver` | `designs`, `design_identifiers`, `design_names` |
| **Device** | `dev_silver` | `devices`, `device_identifiers`, `device_names` (added 2026-04-21) |

**Resolve functions** (STABLE PARALLEL SAFE, ≤10ms p99 target SC-004) — all return `bigint`:
`mol_silver.resolve_molecule`, `resolve_drug_product`, `resolve_company`, `resolve_target`;
`hcs_silver.resolve_provider`, `resolve_facility`;
`ind_silver.resolve_condition`;
`hcp_silver.resolve_researcher`;
`ip_silver.resolve_patent`, `resolve_trademark`, `resolve_design`;
`dev_silver.resolve_device`.

**Key rules**:
- Silver models MUST obtain entity IDs by indexed equi-join to a hub crosswalk OR by calling a resolve function (FR-014). Never by inline fuzzy matching.
- 5 banned antipatterns: S1 (OR-join hub IDs), S2 (leading-wildcard LIKE), S3 (correlated scalar subquery), S4 (DISTINCT ON over UNION ALL), S5 (similarity + = in OR).
- `mol_silver.molecule_aliases` and `mol_silver.identifier_mappings` are being phased out — use `molecule_names` and `molecule_identifiers` instead.

**Bootstrap procedures**: `src/dk_data/sql/migrations/189_bootstrap_*.sql` through `200_bootstrap_*.sql`
**Runbook**: `docs/runbooks/silver-hub-bootstrap.md`
