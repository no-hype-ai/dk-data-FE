# Requirements Checklist: Admin App Integration Fix

**Purpose**: Verify all functional requirements for db-init fix and Compass API views
**Created**: 2026-02-01
**Feature**: [spec.md](../spec.md)

## Database Initialization

- [ ] CHK001 db-init job uses `\$\$` escaping for PL/pgSQL DO blocks (FR-001)
- [ ] CHK002 db-init creates authenticator role (FR-002)
- [ ] CHK003 db-init creates web_anon role (FR-002)
- [ ] CHK004 db-init creates analyst role (FR-002)
- [ ] CHK005 db-init creates api_user role (FR-002)
- [ ] CHK006 db-init creates readonly role (FR-002)
- [ ] CHK007 db-init uses IF NOT EXISTS for idempotency (FR-003)
- [ ] CHK008 db-init can run multiple times without errors (FR-003)

## API Views

- [ ] CHK009 api.molecules view exists with correct columns (FR-004)
- [ ] CHK010 api.resolution_queue view exists with correct columns (FR-005)
- [ ] CHK011 api.data_sources view contains real data, not placeholder (FR-006)
- [ ] CHK012 All views have appropriate GRANT statements (FR-007)

## Role Permissions

- [ ] CHK013 web_anon has SELECT on api.health (FR-008)
- [ ] CHK014 web_anon has SELECT on api.molecules (FR-008)
- [ ] CHK015 web_anon has SELECT on api.data_sources (FR-008)
- [ ] CHK016 web_anon does NOT have SELECT on api.resolution_queue
- [ ] CHK017 analyst has SELECT on api.resolution_queue (FR-009)
- [ ] CHK018 api_user has SELECT on api.resolution_queue (FR-009)

## Admin App Integration

- [ ] CHK019 Health check caches status for 30 seconds (FR-010)
- [ ] CHK020 PostgREST loads 8+ Relations in schema cache (SC-001)
- [ ] CHK021 All PostgREST pods show Running status (SC-002)
- [ ] CHK022 /health endpoint responds within 100ms (SC-005)
- [ ] CHK023 db-init job exits with code 0 (SC-006)

## Notes

- Check items off as completed: `[x]`
- FR-### references functional requirements in spec.md
- SC-### references success criteria in spec.md
