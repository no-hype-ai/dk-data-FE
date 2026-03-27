# Research: CMS PUF & Platform Data Reconciliation

**Phase**: 0 — Research
**Feature**: `019-cms-puf-platform-reconciliation`
**Date**: 2026-03-27

---

## 1. BaseFetcher Retry Logic — Already Implemented

**Decision**: FR-016a (retry-with-backoff in BaseFetcher) is substantially already satisfied on main.

**Finding**: `src/dk_data/ingestion/fetchers/base.py` constructs a `requests.Session` with:

```python
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
```

This gives all subclasses automatic retry-with-exponential-backoff (delays: 0s, 1s, 2s) on `429` and server errors. No per-fetcher changes needed.

**Delta required**: The spec clarification asked for per-source configurable `max_retries` / `retry_base_delay_seconds` in the `SOURCES` dict. Since `BaseFetcher.__init__` builds the `Retry` object with hardcoded values, per-source config would require a small extension: read `max_retries` / `retry_base_delay_seconds` from `SOURCES` config and pass to `Retry` in the session setup. Estimated: ~15 lines in `main.py` + no changes to individual fetchers.

**Rationale**: Centralised in `BaseFetcher` (as clarified); per-source config read from `SOURCES` entry at `run_ingestion()` time and injected via constructor kwarg or session reconfiguration.

**Alternatives considered**: Per-fetcher implementation — rejected (duplication across 28+ fetchers); no retry (rejected by clarification Q3).

---

## 2. trial_outcomes.sql — References xenon on Main

**Decision**: `mol_gold.trial_outcomes` must be updated to remove the `xenon.publication_evidence` reference and replace it with `mol_silver.publication_evidence`.

**Finding**: `src/dk_data/sqlmesh/models/molecules/gold/trial_outcomes.sql` on main already exists and contains:

```sql
FROM xenon.publication_evidence pe
WHERE pe.confidence_score >= 0.40
```

This is the exact dependency FR-024a and FR-033 require us to eliminate. The file is **not** marked `.removed` on main — it exists and is active. The 016 branch had removed it; main restored a version that still references xenon.

**Delta required**: Update `trial_outcomes.sql` to JOIN against `mol_silver.publication_evidence` instead of `xenon.publication_evidence`. The table `mol_silver.publication_evidence` does not yet exist on main — it is created by the consolidated migration.

**Grain correction**: Main `trial_outcomes.sql` uses `grain (molecule_id, trial_nct_id, evidence_source)`. The spec defines `grain (molecule_id, trial_nct_id, endpoint_name, evidence_source)`. The more granular grain is correct — one trial can have multiple endpoints; using `endpoint_name` as part of the grain prevents collapsing endpoints into a single row.

**Rationale**: Adding `endpoint_name` to the grain is a non-breaking change (more rows, not fewer). Removing xenon dependency is the primary correctness goal.

---

## 3. SOURCES Dict — File-Based Sources Have No `fetcher` Key

**Decision**: The spec's Canonical Ingestion Patterns section is correct; however, the code shows that file-based sources in the actual `SOURCES` dict do **not** include a `fetcher` key.

**Finding**: In `src/dk_data/ingestion/main.py`:
- File-based sources (`requires_file: True`): keys are `name`, `description`, `loader`, `requires_file`, optionally `meta_name`, `requires_fiscal_year`
- API sources (`requires_file: False`): add `fetcher` and `default_days_back`

The 28 CMS PUF sources are file-based. Their SOURCES entries will **not** have a `fetcher` key. The file download happens externally (CronJob downloads to a mounted volume; loader is called with the file path).

**Rationale**: CMS PUF files are bulk annual releases (not streamed APIs). The file acquisition is a separate operational step from the SQL load. Keeping them separate preserves the existing architecture.

**Impact on spec**: The Canonical Ingestion Patterns code example showing both `fetcher`-bearing and file-only entries is correct as written. No spec change needed.

---

## 4. Migration Number — Next Is 085

**Decision**: The consolidated migration script will be `085_cms_puf_platform_reconciliation.sql`.

**Finding**: The latest migration on main is `084_add_response_hash_columns.sql`. All prior 016 migrations (001–057 in the 016 branch numbering) must be audited against current main schema. Only the delta — schemas, tables, and columns that do not yet exist on main — goes into 085.

**Rationale**: Single consolidated migration per FR-020. The 016 branch had 57 migrations; many reference dropped schemas or columns that no longer apply (per FR-021). A fresh delta-only migration avoids replay failures.

**Key new objects in 085**:
- `hcs_raw` schema + 7 CMS raw tables (if not created by 084 or earlier)
- `hcs_bronze` schema + bronze models (managed by SQLMesh, not migration — schema creation only)
- `hcs_silver`, `hcs_gold` schemas
- `mol_silver.publication_evidence` table
- `mol_silver.physician_payments` table (if not on main)
- `mol_silver.research_grants` table (if not on main)
- Agent quarantine table: `mol_silver.agent_quarantine`
- `meta.data_sources` INSERT rows for all 28 new CMS sources + 6 new API sources

---

## 5. PostgREST Schema Exposure — Config Location

**Decision**: The PostgREST `db-schemas` config is set via a Doppler-managed environment variable injected into the PostgREST deployment; schema additions require a Doppler project update and a PostgREST pod restart.

**Finding**: PostgREST is deployed as a K8s service. Schema exposure is controlled by `PGRST_DB_SCHEMAS` env var (comma-separated list). Current exposure includes `mol_bronze`, `mol_silver`, `mol_gold` and HCS equivalents will be added in this PR.

**Delta required**: Add `hcs_bronze`, `hcs_silver`, `hcs_gold` (and any `ind_` prefixed schemas when introduced) to `PGRST_DB_SCHEMAS`. Update PostgREST K8s manifest or Doppler config. Raw schemas (`mol_raw`, `hcs_raw`) must never appear in this list.

---

## 6. Grafana Alert Delivery — monitoring/provisioning

**Decision**: The pipeline failure alert rule (FR-034) should be provisioned via `monitoring/provisioning/` using Grafana's provisioning file format.

**Finding**: `monitoring/provisioning/grafana-data-platform.yaml` exists. Grafana alerts can be provisioned alongside dashboards. The alert rule queries `meta.refresh_log` for N consecutive failures using a PostgreSQL datasource query.

**Delta required**: Add `monitoring/provisioning/alerts/pipeline-source-failures.yaml` with a Grafana alert group. The alert fires when `COUNT(*) FILTER (WHERE status = 'failed') >= 3` for any `source_id` in the last N most-recent rows of `meta.refresh_log`.

---

## 7. Agent System — Existing `agents/` Directory Is Empty

**Finding**: `src/dk_data/agents/` exists but contains only `__pycache__`. The 7 agents from the 016 branch were never ported. All 7 agent files must be written from scratch in this PR, following the LiteLLM proxy routing pattern and the BaseFetcher-parallel pattern for agent base classes.

**Agent inventory** (FR-024):
1. `service_line_inference.py` — DRG claims → clinical service line assignments
2. `idn_hierarchy.py` — facility grouping → IDN parent-child relationships
3. `referral_network.py` — claims patterns → referral flow graph
4. `contact_verification.py` — NPI records → verified contact attributes
5. `staffing_decomposition.py` — cost report staffing → role decomposition
6. `equipment_inventory.py` — claims codes → implied equipment inventory
7. `publication_evidence_extractor.py` — publication abstracts → structured clinical endpoints → `mol_silver.publication_evidence`

---

## 8. SQLMesh Model Paths — HCS Models Need New Directory

**Finding**: Current SQLMesh model tree:
```
src/dk_data/sqlmesh/models/molecules/{bronze,silver,gold}/
```

There is no `hcs/` directory. New HCS models need:
```
src/dk_data/sqlmesh/models/hcs/{bronze,silver,gold}/
```

SQLMesh discovers models by scanning `models/` recursively, so subdirectory structure is arbitrary — the `MODEL(name hcs_bronze.cms_part_d_spending)` declaration in the file controls the schema, not the directory path. Convention aligns directory name with schema namespace.

---

## 9. Existing Bronze Models to Leverage or Extend

**Finding**: Several relevant bronze models already exist on main:
- `molecules/bronze/ema.sql` — EMA regulatory; needs review to confirm it maps to `mol_bronze.ema_regulatory` namespace
- `molecules/bronze/cochrane_reviews.sql` — already ingesting Cochrane
- `molecules/bronze/drugbank.sql` — already exists
- `molecules/bronze/sec_edgar.sql` — already exists

**Delta**: CMS PUF sources are new (no existing bronze). EuropePMC and NIH Reporter are new. Existing bronze models may need namespace alignment checks (e.g., `ema.sql` may declare `name molecules.ema` rather than `mol_bronze.ema_regulatory`).

---

## 10. LiteLLM Integration — Agent Call Pattern

**Decision**: All LLM calls in new agents MUST use the LiteLLM proxy via the OpenAI-compatible endpoint. The `anthropic` Python SDK MUST NOT be imported in any new agent or loader file introduced by this feature.

**Finding**: Three existing files (`claude_sdk/enrichment.py`, `claude_sdk/scoring_agent.py`, `iva_evidence_report_workflow.py`) import `anthropic` directly — this is a pre-existing CANON violation in `claude_sdk/`. New agents introduced by this feature must not extend this pattern.

**LiteLLM proxy address**:
- K8s (prod/staging): `http://litellm.infra.svc.cluster.local:8000/v1`
- Bare-metal / local dev: `http://192.168.10.50:4000/v1`
- Env var: `LITELLM_PROXY_URL` (Doppler-sourced, project `dk-data-fe`)

**Model aliases** (use these strings only — never hardcode provider model IDs):
- `pharma-llm` — local/cheap model (first attempt)
- `claude-sonnet-4-20250514` — frontier model (escalation)
- `gpt-4o-mini` — lightweight classification

**Shared rate limit**: 500 RPM across all DataKinetic services. Agents MUST implement exponential backoff on `429` responses. With 7 agents potentially running simultaneously, each agent should pace its LLM calls (max 5 concurrent per agent run) and use `tenacity` for retry logic on the LiteLLM call layer.

**Call pattern** (using `openai` SDK pointed at LiteLLM):
```python
from openai import OpenAI
import os

client = OpenAI(
    base_url=os.environ["LITELLM_PROXY_URL"],
    api_key=os.environ["LITELLM_API_KEY"],   # LiteLLM virtual key from Doppler
)
```

**Quality escalation** (ARCHITECTURE-BEST-PRACTICES.md mandate): Call `pharma-llm` first; if confidence score < 0.6, re-call with `claude-sonnet-4-20250514`. One escalation maximum per record.

**Tenacity vs urllib3.Retry**: `urllib3.Retry` is for HTTP fetchers (BaseFetcher already uses it for downstream data source calls). `tenacity` is for LLM call retry in agents (handles `RateLimitError`, `APIStatusError` 429 from LiteLLM). These are separate retry layers with no overlap.

**Rationale**: CANON mandates "Never call OpenAI/Anthropic directly; use LiteLLM virtual key via Doppler." All 7 new agents must comply. The openai SDK pointing at LiteLLM is the canonical Python pattern for dk-data-FE.

**Alternatives considered**: Anthropic SDK with proxy URL — rejected (CANON violation, wrong client library); direct httpx calls — acceptable but openai SDK provides better error types for 429 handling.

---

## Summary of Research Decisions

| Topic | Decision | Action Required |
|---|---|---|
| BaseFetcher retry | Already implemented; extend for per-source config | ~15 lines in main.py |
| trial_outcomes.sql | Exists on main, references xenon — update required | Edit SQL file, fix grain |
| SOURCES file-based | No `fetcher` key for file-based sources | Correct — no spec change needed |
| Migration number | Next migration is 085 | Write 085_cms_puf_platform_reconciliation.sql |
| PostgREST config | Doppler env var — add hcs_silver/hcs_gold only | Update configmap.yaml (hcs_bronze excluded) |
| Grafana alert | Provisioning file at monitoring/provisioning/alerts/ | New YAML file |
| Agents directory | Empty on main — all 7 agents must be written | 7 new Python files |
| HCS SQLMesh path | New hcs/ subdirectory needed | Create directory tree |
| Existing bronze | EMA/Cochrane/DrugBank/EDGAR already exist | Verify namespace alignment |
| Schema naming split | bronze (legacy), mol_bronze (mol-CI), hcs_bronze (new) | All three via config.yaml mappings |
| silver.publications | Existing model — EuropePMC extends as 5th CTE | No new mol_silver.europepmc table |
| MCP duplication | TOOL_REGISTRY + adapters/ already exist | Extend existing files, no new services/data_tools/ |
| LiteLLM agents | openai SDK → LiteLLM proxy; tenacity for retry | No import anthropic in new code; 500 RPM shared limit |
