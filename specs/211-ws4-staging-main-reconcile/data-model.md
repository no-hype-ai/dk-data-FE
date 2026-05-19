# Phase 1 — Data Model & Dispatch State Machine — WS4 SP1

SP1 introduces **no persistent schema changes** (no migration). The "data
model" here is the in-process contract surface.

## Entities

### Source Adapter
| Field | Meaning | Notes |
|---|---|---|
| `source_name` | stable source identifier | existing (feature-015) |
| `raw_table` | unqualified landing table | existing |
| `raw_schema` | schema holding the raw table | existing |
| `normalize(api_response)` | map upstream → raw-row shape | existing — UNCHANGED |
| `db_query(drug_name, db_pool)` | **NEW** optional DB-first serve | additive; default `None` on `BaseAdapter` |

Validation rule: adding `db_query` MUST NOT alter `normalize`, `build_url`,
`build_urls_with_resolution`, or `validate_against_bronze` (feature-015 surface
preserved — FR-001/FR-005).

### Tool Registry (existing, unchanged)
`slug → ToolDefinition{ name, description, tier, raw_table, raw_schema,
adapter_module, api_base_url, input_schema }`. DB-first dispatch resolves
`adapter_module` lazily.

### DB-First Gate (config)
| Field | Type | Default | Meaning |
|---|---|---|---|
| `MCP_DBFIRST_ENABLED` | bool | `false` | global master switch |
| `MCP_DBFIRST_SOURCES` | csv string | `""` | per-source allowlist |

Effective rule: a source `S` uses DB-first **iff** `MCP_DBFIRST_ENABLED` is true
**and** `S ∈ MCP_DBFIRST_SOURCES`.

### DB-First Outcome (metric)
`mcp_dbfirst_outcome_total{source, outcome}`,
`outcome ∈ {served, fallthrough, error, disabled}`.

### Branch Roles (SP2)
`main` = canonical / production-promotion. `staging` = post-reconcile deploy
mirror. `staging-pre-ws4-reconcile` = immutable recovery tag.

### Ingestion Job Set (SP3)
Scheduled fetch/hydrate units; target: single execution feeding the shared
warehouse; consumers are environment-scoped read-only.

## Dispatch State Machine (SP1, per invocation of tool slug → source S)

```
            ┌─────────────────────────────┐
            │  POST /api/v1/mcp-tools/S    │
            └──────────────┬──────────────┘
                           ▼
              gate_on(S)?  ──no──►  EXISTING httpx path (UNCHANGED)   [outcome=disabled]
                  │ yes
                  ▼
        resolve Adapter for S via tool_registry
                  │
        Adapter/db_query present? ──no──►  EXISTING httpx path        [outcome=disabled]
                  │ yes
                  ▼
             await db_query(drug_name, pool)
              │            │            │
        raises│      None/empty│       non-empty dict
              ▼            ▼            ▼
       502 {"stage":   EXISTING       return result
        "db_query"}    httpx path     (no external call)
       [outcome=error] [outcome=      [outcome=served]
       (DO NOT fall     fallthrough]
        through)
```

Invariants:
- Exactly one terminal outcome per invocation.
- `error` never falls through (FR-004) — a DB outage is not a miss.
- `disabled`/missing-adapter/None/empty are indistinguishable to the client
  from today's behavior (FR-003).
- Absent/older adapter module → `disabled` branch, never `error`.
