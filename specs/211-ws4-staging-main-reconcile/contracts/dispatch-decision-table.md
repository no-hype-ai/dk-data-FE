# Contract — DB-First Dispatch Decision Table

The new `dispatch.py` is a **parallel** module. `router.invoke_tool` consults it
only at the single gated pre-check; the existing httpx invoke path is otherwise
byte-unchanged.

| # | gate_on(S) | Adapter+db_query resolvable | db_query result | Terminal outcome | Client-visible vs today |
|---|---|---|---|---|---|
| 1 | false | — | — | existing httpx path | identical |
| 2 | true | no (absent/older module) | — | existing httpx path | identical |
| 3 | true | yes | `None` / empty | existing httpx path | identical |
| 4 | true | yes | non-empty `dict` | return DB result, no external call | served from warehouse |
| 5 | true | yes | raises | `502 {"stage":"db_query"}`, **no fallthrough** | new (intended) error surface |

Metric `mcp_dbfirst_outcome_total{source,outcome}`: rows 1–2 → `disabled`,
row 3 → `fallthrough`, row 4 → `served`, row 5 → `error`.

Public endpoint `POST /api/v1/mcp-tools/{tool}/invoke` request/response schema
is **unchanged** (`[ZVAL]`/`[VERSN]` preserved). Rows 1–3 guarantee FR-003
(zero default behavior change); row 5 enforces FR-004.

`_load_db_adapter` never raises on import/attribute failure (absent adapter is
expected) — that maps to row 2.
