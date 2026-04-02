# Research: Schema Integrity & Platform Stability

**Branch**: `025-schema-integrity-stability` | **Date**: 2026-04-01

## R1: ON CONFLICT Columns for Broken Loaders

**Decision**: Use expression-based UNIQUE indexes on JSONB fields.
**Rationale**: Loaders use `ON CONFLICT ((response_body->>'field'))` syntax. PostgreSQL requires a matching UNIQUE index on the exact same expression — a UNIQUE constraint on a plain column won't match.
**Alternatives considered**:
- Adding a materialized column for the conflict key: Rejected — requires changing loader code AND DDL, higher risk
- Using `ON CONFLICT DO NOTHING`: Rejected — loses upsert semantics, data not updated on re-fetch

**Specific indexes needed**:
| Table | Expression | Loader File |
|-------|-----------|-------------|
| mol_raw.pubchem | `(response_body->>'cid')` | sources/pubchem.py:57 |
| mol_raw.chembl_molecules | `(response_body->>'molecule_chembl_id')` | sources/chembl_molecules.py:59 |
| mol_raw.who_gho | `(response_body->>'IndicatorCode')` | sources/who_gho.py:59 |

## R2: refresh_log Column Name Authority

**Decision**: `refresh_started_at` / `refresh_completed_at` is authoritative.
**Rationale**: Application code (main.py:1159), init_database.sql, and migration 083 all use these names. Only dev-init.sql diverges with `started_at` / `completed_at`.
**Alternatives considered**:
- Changing application code to match dev-init.sql: Rejected — would require changing migration 083 too, and init_database.sql already agrees with the code

## R3: Cochrane API Status

**Decision**: Mark cochrane fetcher as `source_unavailable`.
**Rationale**: The `/api/search?searchBy=search-manager` endpoint returns 404. Cochrane Library has no free JSON API — requires institutional Wiley license.
**Alternatives considered**:
- Scraping HTML: Rejected — fragile, potentially against ToS
- Wiley API integration: Rejected — requires credentials we don't have

## R4: OpenFDA FAERS Date Range

**Decision**: Replace `99991231` with `datetime.now().strftime('%Y%m%d')`.
**Rationale**: FDA API rejects far-future dates with 403. Current date is the standard upper bound for open-ended queries.
**Alternatives considered**:
- Using a fixed near-future date like `20301231`: Rejected — still arbitrary, will eventually need updating
- Removing the date upper bound entirely: Rejected — FDA API requires both bounds in range queries

## R5: IMGT Endpoint Verification

**Decision**: Add HTTP response status check with clear error reporting.
**Rationale**: IMGT periodically reorganizes download URLs. Current URL points to bulk FASTA: `https://www.imgt.org/download/GENE-DB/IMGTGENE-DB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+inframeP`. If unavailable, the fetcher should report the exact URL that failed.
**Alternatives considered**:
- Hardcoding alternative URLs: Rejected — IMGT has no API versioning, URLs change unpredictably

## R6: MCP Base Tool / Adapter Architecture

**Decision**: Fix cross-cutting issues in `base_tool.py`, add `build_url()` overrides in individual adapters.
**Rationale**: `base_tool.py` handles HTTP execution for all adapters. `BaseAdapter.build_url()` in `adapters/base.py` defaults to `?query={drug_name}` which is wrong for most APIs. Each adapter needs its own override with the correct API-specific parameters.
**Alternatives considered**:
- Fixing only base_tool.py: Rejected — each API has unique query syntax, adapter-level overrides are required

## R7: MCP Router

**Decision**: Create `router.py` with tool listing and invocation endpoints.
**Rationale**: PR #190 designed but hasn't merged. We need the router for the `POST /api/v1/data-tools/{tool}/invoke` endpoint to work.
**Alternatives considered**:
- Cherry-picking from PR #190: Rejected — PR may have other changes we don't want; cleaner to implement fresh matching the same design
