# Contract — DB-First Gate Configuration

| Var | Type | Default | Source of truth |
|---|---|---|---|
| `MCP_DBFIRST_ENABLED` | bool (`true`/`false`) | `false` | Doppler `dk-data-staging` & `dk-data-prod`; surfaced via Kustomize overlays |
| `MCP_DBFIRST_SOURCES` | csv of `source_name` | `""` (empty) | same |

**Effective predicate**: `gate_on(S) == MCP_DBFIRST_ENABLED AND S in split(MCP_DBFIRST_SOURCES)`.

**Rules**
- Default state (both unset/empty/false) ⇒ feature fully inert (FR-003).
- Unknown/misspelled source in the list ⇒ that token is inert (no error;
  behaves as off — edge case).
- Both overlays MUST define the vars (default-off) to preserve Environment
  Parity (Constitution II); committed YAML carries only the non-secret default,
  Doppler carries the live value (`[SECRT]`/`[GITOP]`).
- Single global kill-switch: `MCP_DBFIRST_ENABLED=false` disables everything
  with no code deploy (FR-007 rollback lever).
- Changing the gate is an operational action, not a code change; widening
  `MCP_DBFIRST_SOURCES` is gated on the `served`/`error` metric for that source.
