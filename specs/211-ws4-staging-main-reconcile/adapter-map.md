# SP1 Adapter Map & DB-Handle Wiring (T004/T005)

## DB handle (T005)

`dispatch.try_db_first` obtains the pool via
`from dk_data.api.dependencies import get_db_pool` → `await get_db_pool()`.
`get_db_pool()` returns `Optional[asyncpg.Pool]` (None when asyncpg absent or
pool init failed). **None pool ⇒ no DB path ⇒ outcome=disabled ⇒ existing
httpx path** (never an error). No new pool/lifecycle introduced (R1, `[DSN]`).

## Graft rule

For each source below: into `main`'s **existing** `class Adapter(BaseAdapter)`
in `src/dk_data/services/mcp/adapters/<module>.py`, add (additively, preserving
every existing method incl. any `build_url`/`normalize` override):
- module-level query constant `_DB_LOOKUP_QUERY`
- `from typing import Any` (if absent)
- `async def db_query(self, drug_name, db_pool) -> dict | None` — verbatim from
  `/tmp/ws4-port-source.md` → `### <module>.py`.

`ema_labels` is **absent on `main`** → create the new file verbatim from the
digest (it is refined / non-placeholder).

## Targets (29 = 28 existing-Adapter grafts + 1 new)

| module | main shape | port kind | placeholder ILIKE |
|---|---|---|---|
| ema | Adapter + EmaTool | **refined** (verbatim) | no |
| ema_labels | **NEW FILE** | **refined** (verbatim) | no |
| openfda_labels | Adapter | **refined** (verbatim) | no |
| chembl, clinicaltrials, drugbank, openfda_faers, pubmed, openalex, uniprot, pubchem, orange_book, uspto_patents, epo_patents, sec_edgar, who_icd, orcid (Adapter+OrcidTool), pdb_structures (Adapter+PdbStructuresTool), hta_decisions (Adapter+HtaDecisionsTool), cochrane (Adapter+CochraneTool), acc_tvc, cms_cost_reports, cms_hospital_info, cms_inpatient, hrsa, journal_rss, medical_news, euipo_trademarks, uspto_trademarks | existing `class Adapter` | placeholder graft | yes |

26 placeholder + 3 refined = 29. **Not ported** (staging has no db_query):
`fda_drugs`, `cms_part_d_spending`, `ttd` — tool-only, leave untouched.

## Gate ↔ slug

Gate keys on the **router slug** (e.g. `ema-search`). `tool_registry.TOOL_REGISTRY[slug].adapter_module`
→ lazy `Adapter`. Only the 8 router slugs can actually reach the hook; their
adapter_modules all export `Adapter` (verified). Unknown/misspelled gate token
⇒ inert.
