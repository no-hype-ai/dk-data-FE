# Webhook Contract: <Event Name>

> Formal contract for an async event / webhook delivery.
> Drop into `.dk/specs/<feature>/contracts/` and fill in.

## Purpose

<One-sentence description of what event this represents and which consumers care about it.>

## Trigger Events

| Event | When it fires | Source |
|-------|---------------|--------|
| `<event.name>` | <precondition> | <service that emits> |

## Delivery

- **Transport**: HTTPS POST (JSON body)
- **Delivery guarantee**: <at-least-once | at-most-once | exactly-once>
- **Ordering**: <guaranteed per-resource | best-effort | unordered>
- **Retry policy**: <exponential backoff, max N attempts over M minutes>
- **Timeout**: <seconds before considered failed>

## Payload

```json
{
  "event_id": "string (uuid, unique per delivery)",
  "event_type": "<event.name>",
  "timestamp": "ISO-8601 UTC",
  "data": {
    "field": "type"
  },
  "metadata": {
    "source": "<service>",
    "version": "1.0"
  }
}
```

## Security

- **Signing**: HMAC-SHA256 signature in `X-Signature` header
- **Secret source**: <how consumer obtains the verification secret>
- **Verification**: consumer MUST reject deliveries where the signature does not match

Example verification (pseudocode):

```
signature = hmac_sha256(secret, request_body)
if signature != request.headers["X-Signature"]:
    return 401
```

## Consumer Requirements

- MUST respond with 2xx within the timeout for successful processing
- MUST be idempotent on `event_id` (de-dupe by `event_id` for ≥ 24 hours)
- MUST NOT return 2xx before persisting the event
- SHOULD return non-2xx to trigger retry for transient failures

## Invariants

- <Guarantee 1 — e.g., "event.created is never emitted without a prior event.requested"></li>
- <Guarantee 2 — e.g., "All events for a given resource are delivered in creation order"></li>

## Tags

Active principle tags this contract honors: `[IDMPT]`, `[AUDIT]`, `[STRM]`
