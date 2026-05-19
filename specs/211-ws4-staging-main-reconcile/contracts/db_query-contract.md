# Contract — `BaseAdapter.db_query`

```
async def db_query(self, drug_name: str, db_pool) -> dict | None
```

**Inputs**
- `drug_name`: the query string from the validated `InvokeRequest`.
- `db_pool`: an async DB handle from `main`'s existing DB lifecycle (R1).

**Outputs / outcomes (total, mutually exclusive)**
| Return / behavior | Meaning | Dispatcher action |
|---|---|---|
| `None` | no local path / no match / empty result | fall through to existing external path |
| non-empty `dict` | served from warehouse | return it; **no external call** |
| **raises** | real error (DB outage, query failure) | surface `502 {"stage":"db_query"}`; **never fall through** |

**Default**: `BaseAdapter.db_query` returns `None` (no DB path). Adapters
override to implement DB-first.

**Rules**
1. MUST NOT catch-and-return-`None` to mask a genuine error (that would make a
   DB outage indistinguishable from "not found" — FR-004).
2. An empty/zero-row query result MUST be returned as `None`, not an empty
   `dict` (R4 — no "served empty success").
3. MUST NOT perform external HTTP (that is the fallthrough path's job).
4. MUST NOT mutate adapter `normalize`/feature-015 behavior (FR-001).
5. The 24 backlog adapters use the documented placeholder serving query and
   remain gated off until each source's real bronze/silver query lands.
