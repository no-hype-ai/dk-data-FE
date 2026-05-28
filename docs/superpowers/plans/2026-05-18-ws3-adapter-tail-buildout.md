# WS3 — Adapter-Tail Build-Out (Execution Plan)

**Parent plan:** `2026-05-18-pr415-mcp-db-adapter-remediation.md` §6 / §7.3 (LOCKED:
parallel sub-agent batches, I review+merge each green). Base: **`origin/staging`**
(`57a8d98` + image bump `5e69588`; Phase 0 #420 / Phase 1 #421 / hotfix #422 merged).

## End state (definition of done)
`tests/test_mcp_adapters.py` 29-row matrix fully **real-pass, zero adapter xfail**:
all 29 `ADAPTER_MODULES` in `BUILT_ADAPTERS`, the 6 dedicated `@xfail` test classes
(clinicaltrials, chembl, drugbank, openfda_faers, pubmed, sec_edgar) un-xfailed.
Local baseline that must NOT regress: **27 failed / 874 passed / 36 xfailed / 5 errors**
(`--ignore=tests/test_mcp_data_tools.py --ignore=tests/test_metering_proxy.py`;
the 27F/5E are live-PostgREST noise that PASS in CI's DB service).

## Architecture (verified)
Router is **already fully registry-driven**. `dispatch.py:_load_db_adapter()` lazily
imports `tool_registry.TOOL_REGISTRY[slug].adapter_module`, duck-types for
`Adapter(BaseAdapter)`. **Building an adapter = (1) write `class Adapter(BaseAdapter)`
in the module file the registry already points at; (2) flip it in `BUILT_ADAPTERS`.**
No edits to `router.py` / `dispatch.py` / `tool_registry.py` / `adapters/__init__.py`.
Sole cross-batch shared file: `tests/test_mcp_adapters.py` (the `BUILT_ADAPTERS` set +
6 class-level `@pytest.mark.xfail` decorators) — conflicts resolved by me at merge.

## Per-adapter `Adapter` contract (exact — no subagent fabrication)
`source_name` = module name. `raw_table` / `raw_schema` from the registry (below).
`normalize(api_response: dict) -> dict` = passthrough (`return api_response`).
`db_query(drug_name, db_pool)` honors BaseAdapter: query `{raw_schema}.{raw_table}`
via the verified `mol_raw`/`hcs_raw` JSONB `response_body` serving convention
(the one built/verified pattern — see `openfda_labels.Adapter._db_lookup`); **no rows
⇒ return None** (router falls through / structured 404), **DB error ⇒ raise** (never
swallow to None — that is the H1 silent-failure class → dispatch 502 `stage:db_query`).
HTTP `_api_lookup` fallback is **intentionally out of WS3 scope** for the backlog tail
(consistent with `ema-labels` by-design 404-on-miss + parent-plan deferred items).
Decision rationale: 26 raw-table schemas cannot be verified without DB introspection;
fabricating per-source SQL is precisely the silent-failure anti-pattern being remediated.

### Registry contract table (module → slug / raw_table / raw_schema)
| module | slug | raw_table | raw_schema | file |
|---|---|---|---|---|
| clinicaltrials | clinicaltrials-search | clinicaltrials | mol_raw | NEW; dedicated @xfail class |
| chembl | chembl-search | chembl | mol_raw | NEW; dedicated @xfail class |
| openfda_faers | openfda-faers-search | openfda_faers | mol_raw | NEW; dedicated @xfail class |
| drugbank | drugbank-search | drugbank | mol_raw | NEW; dedicated @xfail class |
| pubmed | pubmed-search | pubmed | mol_raw | NEW; dedicated @xfail class |
| sec_edgar | sec-edgar-search | sec_edgar | mol_raw | NEW; dedicated @xfail class |
| openalex | openalex-search | openalex | mol_raw | NEW |
| uniprot | uniprot-search | uniprot | mol_raw | NEW |
| orange_book | orange-book-search | orange_book | mol_raw | NEW |
| uspto_patents | uspto-patents-search | uspto_patents | mol_raw | NEW |
| epo_patents | epo-patents-search | epo_patents | mol_raw | NEW |
| pubchem | pubchem-search | pubchem | mol_raw | NEW |
| who_icd | who-icd-search | who_icd | mol_raw | NEW |
| journal_rss | journal-rss-fetch | journal_rss | mol_raw | NEW |
| medical_news | medical-news-fetch | medical_news | mol_raw | NEW |
| uspto_trademarks | uspto-trademarks-search | uspto_trademarks | mol_raw | NEW |
| euipo_trademarks | euipo-trademarks-search | euipo_trademarks | mol_raw | NEW |
| cms_inpatient | cms-inpatient-search | cms_medicare_inpatient | hcs_raw | NEW |
| cms_hospital_info | cms-hospital-info-search | cms_hospital_info | hcs_raw | NEW |
| cms_cost_reports | cms-cost-reports-search | cms_cost_reports | hcs_raw | NEW |
| acc_tvc | acc-tvc-search | acc_tvc_certification | hcs_raw | NEW |
| hrsa | hrsa-search | hrsa_shortage_areas | hcs_raw | NEW |
| hta_decisions | hta-decisions-search | hta_decisions | mol_raw | EXISTS (stub *Tool) — add Adapter |
| cochrane | cochrane-search | cochrane_reviews | mol_raw | EXISTS (stub *Tool) — add Adapter |
| orcid | orcid-search | orcid | mol_raw | EXISTS (stub *Tool) — add Adapter |
| pdb_structures | pdb-search | pdb_structures | mol_raw | EXISTS (stub *Tool) — add Adapter |

Existing-stub files: keep the `*Tool(BaseMCPTool)` class intact (imported by
`adapters/__init__.py`); add `class Adapter(BaseAdapter)` alongside it.

## Test pattern (mandatory — green everywhere)
Mirror `tests/test_adapter_openfda_labels.py`: plain sync tests driving coroutines
with `asyncio.run`; hand-rolled `_FakePool`/`_FakeConn`/`_FakePoolRaises`; **no
`@pytest.mark.asyncio`, no `respx`, no real DB**. Each `tests/test_adapter_<m>.py`:
contract props; `normalize` passthrough; db_query hit→dict; miss(empty rows)→None;
DB error→raises (H1). TDD: RED (no `Adapter`) → minimal GREEN → commit.

## Batches (26 backlog → 6 PRs; base `origin/staging`; PR base = `staging`)
- **PR-0 (SOLO, FIRST):** landmine fix — snapshot/restore `sys.modules` for `dk_data*`
  around the module-level `_load()` block in `tests/test_mcp_data_tools.py` so canonical
  names aren't left polluted after collection; reformat `BUILT_ADAPTERS` one-name-per-line
  sorted. Regression test: importing `tests.test_mcp_data_tools` leaves
  `sys.modules["dk_data.services.mcp.adapters"]` either absent or the real package (not a
  stub). Verify deterministic repro green.
- **Batch A (5):** clinicaltrials, chembl, drugbank, openfda_faers, pubmed
- **Batch B (5):** sec_edgar, hta_decisions, cochrane, orcid, pdb_structures
- **Batch C (6):** openalex, uniprot, orange_book, uspto_patents, epo_patents, pubchem
- **Batch D (5):** who_icd, journal_rss, medical_news, uspto_trademarks, euipo_trademarks
- **Batch E (5):** cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc, hrsa

## Execution & merge protocol
PR-0 solo subagent-driven (impl → spec review → quality review → fixes re-reviewed).
Then build batches via parallel sub-agents (worktree per batch off latest
`origin/staging`); subagent-driven discipline inside each batch. **Serial verified
merge:** per PR — `gh pr checks <#>` shows `Test` **pass** AND `Lint` pass (NEVER rely
on auto-merge; `staging` has NO branch protection), local deterministic repro green,
then rebase on latest `origin/staging`, resolve the deterministic `test_mcp_adapters.py`
union (BUILT_ADAPTERS additions + class-xfail removals), squash-merge. Update the
memory file + `MEMORY.md` after each merge. CI never red at any step.

## Carry-forwards / governance
- `staging` has **zero branch protection** (worse than "Test not required"): surface to
  human — make `Test`+`Lint` required status checks on `staging`.
- Parent-plan deferred items (ema exact-match; openfda_labels._api_lookup swallow;
  ema_labels ingested_at=None TTL; ema_mol pandas header; ema-labels 404-by-design):
  re-confirm acceptable; not blocking WS3.
- After WS3: WS4 = write `2026-05-18-ws4-staging-main-reconcile.md` + execute.
