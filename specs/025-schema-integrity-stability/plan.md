# Implementation Plan: Schema Integrity & Platform Stability

**Branch**: `025-schema-integrity-stability` | **Date**: 2026-04-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-schema-integrity-stability/spec.md`

## Summary

Fix 4 categories of post-deployment failures: (1) DDL/schema drift — align `meta.refresh_log` column names, add missing UNIQUE constraints for ON CONFLICT upserts, verify missing tables exist; (2) CronJob OOMKills — bump memory limits for 5 jobs; (3) broken external API fetchers — fix cochrane/openfda_faers/imgt endpoints; (4) MCP adapter failures — fix base_tool defaults + 5 adapter `build_url()` overrides + 3 bulk-only graceful errors. Cross-cutting: verify table prefix consistency and no column loss across medallion layers.

## Technical Context

**Language/Version**: Python 3.11+, SQL (PostgreSQL 16.4), YAML (Kubernetes manifests)
**Primary Dependencies**: FastAPI, psycopg2-binary, SQLMesh, httpx (MCP adapters), PostgREST v12.2.3
**Storage**: PostgreSQL 16.4 via CloudNativePG (`postgresql.infra.svc.cluster.local:5432`, database `dk_data`)
**Testing**: pytest (unit/integration), manual cluster verification via kubectl
**Target Platform**: K3s Kubernetes cluster (staging + prod)
**Project Type**: Single monorepo — ingestion layer + API + MCP services + K8s manifests
**Performance Goals**: All 61+ sources ingest without error; zero OOMKills
**Constraints**: Migrations must be idempotent (IF NOT EXISTS / IF EXISTS patterns); CronJob memory within node allocatable limits
**Scale/Scope**: 106 fetchers, 238 SQLMesh models, 137 existing migrations, 144 CronJob YAMLs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Local constitution is a blank template. However, dk-canon (`/Users/pschloz/Desktop/DataKinetic/Cross-Project-Planning/dk-canon/CANON.md`) defines dk-data-FE-specific rules:
- SQL must use named dollar-quoting (`$migrate$`, not staged `$$`)
- Namespaces: `dk-data-staging` / `dk-data-prod`
- db-init must preserve API views (api.health, api.data_catalog, api.targets, api.scoring, api.data_sources)
- Feature branch must pass 10-item checklist before merge
- Staging validation via `validate-staging-ingestion.sh`
- meta.data_sources must have entries for all ingested sources

All gates pass with the amendments applied in this audit.

## Project Structure

### Documentation (this feature)

```text
specs/025-schema-integrity-stability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A — no new API endpoints)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/dk_data/
├── ingestion/
│   ├── main.py                          # Orchestrator — refresh_log INSERT
│   ├── fetchers/
│   │   ├── cochrane.py                  # FR-014: fix 404 endpoint
│   │   ├── openfda_faers.py             # FR-015: fix date range
│   │   └── imgt.py                      # FR-016: verify URL
│   └── sources/
│       ├── pubchem.py                   # ON CONFLICT (response_body->>'cid')
│       ├── chembl_molecules.py          # ON CONFLICT (response_body->>'molecule_chembl_id')
│       └── who_gho.py                   # ON CONFLICT (response_body->>'IndicatorCode')
├── services/mcp/
│   ├── adapters/
│   │   ├── base.py                      # FR-017/18/19: fix defaults
│   │   ├── fda_drugs.py                 # FR-020: add build_url()
│   │   ├── pdb_structures.py            # FR-020: add build_url()
│   │   ├── orcid.py                     # FR-020: add build_url()
│   │   ├── cms_part_d_spending.py       # FR-020: add build_url()
│   │   ├── hta_decisions.py             # FR-020: add build_url()
│   │   ├── ema.py                       # FR-021: bulk-only message
│   │   ├── cochrane.py                  # FR-021: bulk-only message (has build_url override)
│   │   └── ttd.py                       # FR-021: bulk-only message
│   └── base_tool.py                     # Cross-cutting HTTP fixes
├── sql/
│   ├── init_database.sql                # FR-001: fix refresh_log columns
│   └── migrations/
│       └── 138_schema_integrity.sql     # New migration: constraints + DDL
scripts/
└── dev-init.sql                         # FR-001: fix refresh_log columns

k8s/apps/cronjobs/base/
├── cronjob-fetch-sider.yaml             # FR-009: 512Mi → 1Gi
├── cronjob-fetch-cms-imaging-puf.yaml   # FR-010: 512Mi → 1Gi
├── cronjob-fetch-cms-pecos.yaml         # FR-011: 512Mi → 1Gi
├── cronjob-fetch-hrsa.yaml              # FR-012: 512Mi → 1Gi
└── cronjob-fetch-cms-formulary.yaml     # FR-013: 2Gi → 4Gi

src/dk_data/sqlmesh/models/              # FR-006: verify column completeness
├── molecules/bronze/*.sql
├── molecules/silver/*.sql
├── hcs/bronze/*.sql
└── hcs/silver/*.sql
```

**Structure Decision**: Existing monorepo structure. No new directories needed — all changes are modifications to existing files plus one new migration.

## Complexity Tracking

No constitution violations. All changes are targeted fixes to existing code/config.

---

## Phase 0: Research

All technical unknowns resolved via codebase exploration:

### R1: ON CONFLICT columns for broken loaders

**Decision**: UNIQUE constraints must be expression-based indexes on JSONB fields, not simple column constraints.
**Rationale**: The loaders use `ON CONFLICT ((response_body->>'cid'))` (pubchem), `ON CONFLICT ((response_body->>'molecule_chembl_id'))` (chembl), and `ON CONFLICT ((response_body->>'IndicatorCode'))` (who_gho). PostgreSQL requires a matching UNIQUE index on the same expression.
**Migration pattern**:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_pubchem_cid
    ON mol_raw.pubchem ((response_body->>'cid'));
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_chembl_molecules_chembl_id
    ON mol_raw.chembl_molecules ((response_body->>'molecule_chembl_id'));
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mol_raw_who_gho_indicator_code
    ON mol_raw.who_gho ((response_body->>'IndicatorCode'));
```

### R2: refresh_log column name authority

**Decision**: Standardize on `refresh_started_at` / `refresh_completed_at` (matching code in main.py line 1159 and init_database.sql).
**Rationale**: The application code is the consumer; the DDL must match.
**Fix**: Update `scripts/dev-init.sql` to rename `started_at` → `refresh_started_at` and `completed_at` → `refresh_completed_at`. Migration 138 will ALTER TABLE for existing clusters.

### R3: Cochrane API status

**Decision**: The Cochrane Library API (`/api/search?searchBy=search-manager`) was removed. No free replacement exists.
**Rationale**: Cochrane requires a Wiley institutional license for API access.
**Fix**: Mark the fetcher as `source_unavailable` with a clear message. The MCP adapter already has a `build_url()` override — update it to return bulk-only message.

### R4: OpenFDA FAERS date range

**Decision**: Replace `99991231` sentinel with today's date formatted as `YYYYMMDD`.
**Rationale**: The FDA API rejects far-future dates with 403. Using today's date is standard practice.
**Fix**: In `openfda_faers.py`, change `TO 99991231` to `TO {today_str}` where `today_str = datetime.now().strftime('%Y%m%d')`.

### R5: IMGT endpoint

**Decision**: Verify the bulk FASTA URL `https://www.imgt.org/download/GENE-DB/IMGTGENE-DB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+inframeP` is still valid. If not, add URL verification with clear error.
**Rationale**: IMGT periodically reorganizes downloads. The fetcher should catch HTTP errors and report the attempted URL.

### R6: MCP base adapter defaults

**Decision**: Fix 3 cross-cutting issues in `src/dk_data/services/mcp/adapters/base.py` (the `BaseAdapter` class, not `base_tool.py`):
- The default `build_url()` appends `?query={drug_name}` which is wrong for most APIs
- `base_tool.py` doesn't explicitly set `follow_redirects` (httpx defaults to True, but PR #190 notes issues)
- No `Accept: application/json` header except for WHO ICD
- Unconditional `response.json()` in `base_tool.py` without content-type check
**Fix**: Update `base_tool.py` to add Accept header, content-type check. Adapter-level `build_url()` overrides go in individual adapter files.

### R7: MCP router

**Decision**: `router.py` does not exist on main (PR #190 not merged). Need to create it or integrate the adapter invocation endpoint.
**Rationale**: Without the router, there's no `POST /api/v1/data-tools/{tool}/invoke` endpoint.
**Fix**: Create `router.py` with tool listing and invocation endpoints, register in FastAPI app.

---

## Phase 1: Design

### Work Packages

#### WP1: Migration 138 — Schema Integrity (FR-001 through FR-004)

**Single idempotent migration file**: `src/dk_data/sql/migrations/138_schema_integrity.sql`

Contents:
1. ALTER `meta.refresh_log` — rename columns if old names exist (DO block with NAMED dollar-quoting per dk-canon: `$migrate$`, not `$$`)
2. CREATE UNIQUE INDEX on `mol_raw.pubchem((response_body->>'cid'))`
3. CREATE UNIQUE INDEX on `mol_raw.chembl_molecules((response_body->>'molecule_chembl_id'))`
4. CREATE UNIQUE INDEX on `mol_raw.who_gho((response_body->>'IndicatorCode'))`
5. CREATE TABLE IF NOT EXISTS `mol_raw.cdc_vaccines` (safety net if migration 121 wasn't applied)
6. INSERT INTO `meta.data_sources` for cdc_vaccines ON CONFLICT DO NOTHING (required for orchestrator source_id lookup)

All statements use IF NOT EXISTS / IF EXISTS for idempotency. All DO blocks use named dollar-quoting per dk-canon.

#### WP2: Init Script Alignment (FR-001)

**Files**: `scripts/dev-init.sql`, `src/dk_data/sql/init_database.sql`
- Ensure both use `refresh_started_at` / `refresh_completed_at`
- `dev-init.sql` currently has `started_at` / `completed_at` — change it

#### WP3: CronJob Memory Bumps (FR-009 through FR-013)

**Files**: 5 CronJob YAMLs in `k8s/apps/cronjobs/base/`

| CronJob | Current Request/Limit | New Request/Limit |
|---------|----------------------|-------------------|
| fetch-sider | 256Mi / 512Mi | 512Mi / 1Gi |
| fetch-cms-imaging-puf | 256Mi / 512Mi | 512Mi / 1Gi |
| fetch-cms-pecos | 256Mi / 512Mi | 512Mi / 1Gi |
| fetch-hrsa | 256Mi / 512Mi | 512Mi / 1Gi |
| fetch-cms-formulary | 512Mi / 2Gi | 1Gi / 4Gi |

#### WP4: Fetcher Fixes (FR-014 through FR-016)

**cochrane.py**: Add early return with `source_unavailable` status and message explaining API was removed; requires Wiley institutional license.

**openfda_faers.py**: Replace `99991231` with `datetime.now().strftime('%Y%m%d')` in the search query.

**imgt.py**: Add HTTP status check after download attempt; if non-200, return structured error with the attempted URL.

#### WP5: MCP Base Tool + Adapter Fixes (FR-017 through FR-021)

**base_tool.py** (3 cross-cutting fixes):
1. Set `follow_redirects=True` explicitly in httpx.AsyncClient
2. Add `Accept: application/json` as default header in all requests
3. Wrap `response.json()` in try/except; check Content-Type first; return structured error for non-JSON

**5 fixable adapters** — add `build_url()` overrides:
- `fda_drugs.py`: `?search=openfda.generic_name:"{drug_name}"&limit=100`
- `pdb_structures.py`: `?json={"query":{"type":"terminal","service":"text","parameters":{"value":"{drug_name}"}},"return_type":"entry"}`
- `orcid.py`: `?q={drug_name}` + explicit `Accept: application/json` header
- `cms_part_d_spending.py`: CMS data-api endpoint with dataset UUID filter
- `hta_decisions.py`: `https://api.nice.org.uk/services/search?q={drug_name}`

**3 bulk-only adapters** — override invoke to return structured message:
- `ema.py`: "EMA data is available via bulk CSV download only. Use the ema_regulatory fetcher pipeline."
- `cochrane.py`: "Cochrane Library requires institutional Wiley API access. Use the cochrane fetcher for bulk ingestion."
- `ttd.py`: "TTD is a flat-file database (domain unreachable outside China). Use the ttd fetcher for bulk download."

**router.py** — create MCP tool invocation endpoint:
- `GET /api/v1/data-tools/` — list registered tools
- `POST /api/v1/data-tools/{tool}/invoke` — invoke a named tool

#### WP6: Column Completeness Audit (FR-006 through FR-008)

Cross-cutting verification pass:
1. For each raw table with domain-specific columns (not envelope pattern), verify bronze model SELECT list includes all columns
2. For envelope-pattern tables (response_body JSONB), bronze models extract from JSONB — verify field names match API docs
3. Verify all table/model prefixes follow convention
4. Document any intentional column omissions

This is an audit task — fixes only if mismatches are found.

### Data Model Changes

No new entities. Changes to existing:

**meta.refresh_log** — column rename:
- `started_at` → `refresh_started_at` (TIMESTAMPTZ)
- `completed_at` → `refresh_completed_at` (TIMESTAMPTZ)

**mol_raw.pubchem** — add unique expression index on `(response_body->>'cid')`
**mol_raw.chembl_molecules** — add unique expression index on `(response_body->>'molecule_chembl_id')`
**mol_raw.who_gho** — add unique expression index on `(response_body->>'IndicatorCode')`

### Contracts

No new API contracts needed. The MCP router exposes:
- `GET /api/v1/data-tools/` — returns `{"tools": [{"name": str, "description": str}, ...]}`
- `POST /api/v1/data-tools/{tool}/invoke` — accepts `{"drug_name": str}`, returns `{"status": str, "data": any, "error": str|null}`

These match the patterns already used in the codebase (PR #190 design).

---

## Implementation Order

1. **WP1 + WP2** (Migration + init scripts) — unblocks all ingestion
2. **WP3** (CronJob memory) — unblocks 5 OOMKilled sources
3. **WP4** (Fetcher fixes) — unblocks 3 broken fetchers
4. **WP5** (MCP adapters) — fixes analyst tooling
5. **WP6** (Column audit) — verification pass, fixes only if needed

WP1-WP3 are independent and can be implemented in parallel. WP4 and WP5 are independent of each other. WP6 depends on WP1 (schema must be stable before audit).
