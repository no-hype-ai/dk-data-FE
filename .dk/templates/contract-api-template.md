# API Contract: <Service Name>

> Formal contract for a REST/JSON API. Drop into `.dk/specs/<feature>/contracts/`
> and fill in. Generated or referenced by `/dk.plan`.

## Purpose

<One-sentence description of what this API does and who consumes it.>

## Authentication & Authorization

- **Auth method**: <Bearer token, session cookie, mTLS, signed request, etc.>
- **Who can call**: <role(s) or tier(s) permitted>
- **Rate limits**: <requests/min per caller or none>

## Endpoints

### `<METHOD> /path/to/resource`

**Purpose**: <what this endpoint does>

**Request headers**:

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | yes | `Bearer <token>` |
| `Content-Type` | yes | `application/json` |

**Request body** (if applicable):

```json
{
  "field_name": "type (constraints)",
  "nested": {
    "field": "type"
  }
}
```

**Response — 200 OK**:

```json
{
  "field": "type"
}
```

**Error responses**:

| Status | Condition | Body |
|--------|-----------|------|
| `400` | invalid input | `{ "error": "<message>", "field": "<name>" }` |
| `401` | missing/invalid auth | `{ "error": "unauthorized" }` |
| `403` | role/tier not permitted | `{ "error": "forbidden" }` |
| `404` | resource not found | `{ "error": "not_found" }` |
| `409` | state conflict | `{ "error": "conflict", "reason": "<detail>" }` |
| `500` | server error | `{ "error": "internal_error", "request_id": "<uuid>" }` |

## Invariants

- <Guarantee 1 — e.g., "GET is idempotent and safe to retry"></li>
- <Guarantee 2 — e.g., "POST requires idempotency-key header for retries"></li>

## Tags

Active principle tags this contract honors: `[TYPED]`, `[RBAC]`, `[AUDIT]`, `[ZVAL]`
