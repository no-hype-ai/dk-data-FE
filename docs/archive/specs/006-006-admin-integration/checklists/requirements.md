# Requirements Checklist: Admin App Integration Fix

**Purpose**: Verify all functional requirements for db-init fix and Compass API views
**Created**: 2026-02-01
**Updated**: 2026-02-01
**Feature**: [spec.md](../spec.md)

## Database Initialization

- [x] CHK001 db-init job uses named dollar-quoting ($role$, $perm$, $iso$) for PL/pgSQL DO blocks (FR-001)
- [x] CHK002 db-init creates authenticator role (FR-002)
- [x] CHK003 db-init creates web_anon role (FR-002)
- [x] CHK004 db-init creates analyst role (FR-002)
- [x] CHK005 db-init creates api_user role (FR-002)
- [x] CHK006 db-init creates readonly role (FR-002)
- [x] CHK007 db-init uses IF NOT EXISTS for idempotency (FR-003)
- [ ] CHK008 db-init can run multiple times without errors (FR-003) - VERIFY IN STAGING

## API Views

- [x] CHK009 api.molecules view exists with correct columns (FR-004)
- [x] CHK010 api.resolution_queue view exists with correct columns (FR-005)
- [x] CHK011 api.data_sources view updated with id, record_count, error_message columns (FR-006)
- [x] CHK012 All views have appropriate GRANT statements (FR-007)

## Role Permissions

- [x] CHK013 web_anon has SELECT on api.health (FR-008)
- [x] CHK014 web_anon has SELECT on api.molecules (FR-008)
- [x] CHK015 web_anon has SELECT on api.data_sources (FR-008)
- [x] CHK016 web_anon does NOT have SELECT on api.resolution_queue (explicit REVOKE)
- [x] CHK017 analyst has SELECT on api.resolution_queue (FR-009)
- [x] CHK018 api_user has SELECT on api.resolution_queue (FR-009)

## Admin App Integration

- [x] CHK019 Health check caching pattern documented (FR-010) - admin-app-patterns.md
- [ ] CHK020 PostgREST loads 7+ Relations in schema cache (SC-001) - VERIFY AFTER DEPLOYMENT
- [ ] CHK021 All PostgREST pods show Running status (SC-002) - VERIFY AFTER DEPLOYMENT
- [ ] CHK022 /health endpoint responds within 100ms (SC-005) - VERIFY AFTER DEPLOYMENT
- [ ] CHK023 db-init job exits with code 0 (SC-006) - VERIFY AFTER DEPLOYMENT

## Notes

- Check items off as completed: `[x]`
- FR-### references functional requirements in spec.md
- SC-### references success criteria in spec.md
- Items marked "VERIFY AFTER DEPLOYMENT" require cluster access
