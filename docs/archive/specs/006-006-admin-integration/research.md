# Research: Admin App Integration Fix

**Feature**: 006-006-admin-integration
**Date**: 2026-02-01
**Purpose**: Resolve NEEDS CLARIFICATION items and document technical decisions

## Research Areas

### 1. Heredoc Escaping in Kubernetes Jobs

**Question**: Why do `DO $$...$$` blocks fail in production but appear to work in staging?

**Investigation**:
1. Reviewed production db-init Job logs:
   ```
   ERROR: syntax error at or near "$"
   LINE 1: DO $
              ^
   ```

2. Analyzed the current db-init-job.yaml structure:
   - Uses bash heredoc `<<'SQL'` (single-quoted, prevents variable expansion)
   - Contains PL/pgSQL `DO $$ ... $$` blocks
   - Multiple shell layers: Kubernetes → container → /bin/bash → psql

3. Key finding: The `$$` delimiter is being interpreted somewhere in the shell pipeline despite single-quoted heredoc. This is a known issue with Kubernetes Jobs where the command array processing can interfere.

**Decision**: Use `\$\$` escaping within the bash script OR use different dollar-quote tags like `$role$`, `$perm$`, etc.

**Rationale**:
- Escaping `\$\$` is explicit and works reliably in bash
- Alternative dollar-quote tags (`$role$`) avoid conflict but are less conventional
- Recommendation: Use `\$\$` for consistency with bash escaping conventions

**Alternatives Considered**:
1. ConfigMap with SQL file mounted as volume - More complex, requires additional resources
2. Individual `psql -c` commands for each statement - Verbose but works, good for simple statements
3. External init container with pre-baked SQL - Requires building custom image

### 2. Staging vs Production Discrepancy

**Question**: Why does staging have 5 Relations but production has 0?

**Investigation**:
1. Staging db-init Job logs show partial success with some errors
2. Production db-init Job logs show complete failure at role creation step
3. Staging likely had manual intervention or partial db-init runs that succeeded

**Decision**: The fix must be fully idempotent and handle both fresh databases and partially-initialized states.

**Rationale**: Both environments should converge to the same state after applying the fix.

### 3. Admin App Expected API Schema

**Question**: What exact endpoints does the Admin App Compass feature expect?

**Investigation**:
1. Reviewed `/Users/nicholas/Code/behavior-labs-ai/ADMIN_APP_ISSUES.md`:
   - `GET /api/compass/search` → proxies to `/molecules`
   - `GET /api/compass/sources` → proxies to `/data_sources`
   - `GET /api/compass/resolution` → proxies to `/resolution_queue`

2. Current dk-data API views:
   - `api.health` ✓ EXISTS
   - `api.data_catalog` ✓ EXISTS
   - `api.targets` ✓ EXISTS (placeholder)
   - `api.scoring` ✓ EXISTS (placeholder)
   - `api.data_sources` ✓ EXISTS (placeholder)
   - `api.molecules` ✗ MISSING
   - `api.resolution_queue` ✗ MISSING

**Decision**: Create `api.molecules` and `api.resolution_queue` views with placeholder data pattern if underlying tables don't exist.

**Rationale**:
- Unblocks Admin App development immediately
- Views can be updated later when real data is available
- Follows existing pattern from `api.targets`, `api.scoring`

### 4. Molecule Table Schema

**Question**: What schema should `api.molecules` expose?

**Investigation**:
1. Admin App TypeScript client expects:
   ```typescript
   interface Molecule {
     id: string;
     smiles: string;
     inchi_key: string;
     name: string;
     molecular_weight: number;
     created_at: string;
     updated_at: string;
   }
   ```

2. Feature 004 (molecule-platform-integration) defines:
   - `mol_gold.molecules` as the canonical molecule store
   - Fields align with Admin App expectations

**Decision**: Create view that selects from `mol_gold.molecules` if it exists, otherwise create placeholder view.

**Rationale**: Forward-compatible with 004 implementation while unblocking Admin App now.

### 5. Resolution Queue Schema

**Question**: What schema should `api.resolution_queue` expose?

**Investigation**:
1. Admin App expects:
   ```typescript
   interface ResolutionItem {
     id: string;
     source_id: string;
     target_smiles: string;
     status: 'pending' | 'in_progress' | 'completed' | 'failed';
     priority: number;
     created_at: string;
     resolved_at: string | null;
   }
   ```

2. Feature 004 defines `mol_app.resolution_queue` table with similar structure.

**Decision**: Create placeholder view matching Admin App expectations.

**Rationale**: Maintains API contract while actual table implementation is separate work.

### 6. Permission Model for Compass Views

**Question**: Which roles should have access to Compass views?

**Investigation**:
1. Current permission model (from 005):
   - `web_anon`: Health, data_catalog only (public)
   - `analyst`: Above + targets, scoring, data_sources
   - `api_user`: Full read access to all api views

2. Compass views security considerations:
   - `api.molecules`: Public molecule data, read-only - OK for web_anon
   - `api.resolution_queue`: Internal workflow data - restrict to analyst/api_user

**Decision**:
- Grant web_anon SELECT on `api.molecules`, `api.data_sources`
- Grant analyst, api_user SELECT on `api.resolution_queue`
- Explicitly REVOKE resolution_queue from web_anon

**Rationale**: Molecule search is public functionality, but resolution workflow is internal.

### 7. Graceful Degradation Pattern

**Question**: How should Admin App handle dk-data unavailability?

**Investigation**:
1. Current behavior: Raw 503 error propagated to UI
2. Best practices:
   - Cache health check results (30-60 second TTL)
   - Return structured error response, not thrown exception
   - Show status indicator in UI
   - Implement circuit breaker for repeated failures

**Decision**: Document recommended patterns in this feature; defer Admin App implementation to separate work.

**Rationale**:
- dk-data fix is blocking and should be prioritized
- Admin App resilience is UX improvement, not blocking
- Admin App team can implement using documented patterns

## Summary of Decisions

| Area | Decision | Confidence |
|------|----------|------------|
| Heredoc escaping | Use `\$\$` escaping in bash | High |
| Production fix | Full idempotent re-run of db-init | High |
| Missing views | Create placeholder views for molecules, resolution_queue | High |
| Molecule schema | Match Admin App TypeScript interface | High |
| Resolution queue schema | Match Admin App TypeScript interface | High |
| Permissions | web_anon gets molecules; analyst/api_user get resolution_queue | High |
| Admin App changes | Document patterns, defer implementation | Medium |

## Next Steps

1. Proceed to Phase 1: Create data-model.md with entity definitions
2. Create contracts/ with OpenAPI specifications
3. Create quickstart.md with verification procedures
