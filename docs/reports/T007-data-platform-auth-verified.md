# T007 — /data-platform/* router is behind `require_auth`

**Feature**: 002-external-integration-foundation (US-15)
**Date**: 2026-04-13
**Status**: PASS

## Check

The FastAPI data-platform router must have router-level
`require_auth` applied so every route inside it is gated.

```bash
grep -n 'Depends(require_auth)' src/dk_data/api/routes/data_platform.py
```

## Result

2 occurrences:

1. **Router declaration**: `router = APIRouter(..., dependencies=[Depends(require_auth)])`
   — every route mounted on this router inherits auth.
2. **Explicit use inside one route handler** — belt-and-suspenders
   for the internal `/job-complete` callback which has its own
   role check on top of the router dependency.

Coverage verified by `tests/test_data_platform_auth.py` (9 tests, all
passing). Router currently has 41 routes (34 pre-existing + 7 resolve
wrappers added by T075 / T076).

## Related

- `src/dk_data/api/routes/data_platform.py`
- `src/dk_data/api/middleware/rbac.py` — `require_auth` implementation
- `tests/test_data_platform_auth.py` — 9 passing tests
- T027, T028 — router-level auth shipped
