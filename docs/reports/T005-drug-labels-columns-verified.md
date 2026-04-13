# T005 — mol_silver.drug_labels inline columns verified

**Feature**: 002-external-integration-foundation (US-4)
**Date**: 2026-04-13
**Status**: PASS

## Check

The US-4 scope correction dropped the originally-planned
`mol_api.boxed_warnings` and `mol_api.contraindications` views in
favor of querying the inline columns on `mol_silver.drug_labels`
directly. This report verifies those columns exist.

```bash
grep -n 'boxed_warning\|contraindications' \
  src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql
```

## Result

Both columns are present in the SQLMesh model. The adapter methods
`molecules.getBoxedWarnings` and `molecules.getContraindications`
both query via `?boxed_warning=not.is.null` and
`?contraindications=not.is.null` filters through PostgREST — no
dedicated view needed.

## Related

- `src/dk_data/sqlmesh/models/molecules/silver/drug_labels.sql`
- `src/dk_data/sql/migrations/216_missing_mol_api_views.sql` — scope correction
- `packages/dk-data-client/python/dk_data_client/modules/molecules.py`
- `packages/dk-data-client/typescript/src/modules/molecules.ts`
