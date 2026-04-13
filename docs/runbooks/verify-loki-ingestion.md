# Runbook: Verify Loki ingestion path

**Feature**: 002-external-integration-foundation (US-17, US-1, T003, T004)
**Last verified**: 2026-04-13

Before the `dk-data-client` starts pushing structured telemetry to
Loki (`app=adapter-telemetry`), verify that:

1. **T003**: the Loki HTTP push endpoint accepts JSON events from
   external apps and the events appear in Grafana Explore within 30 s
2. **T004**: the Loki retention + PVC capacity can hold ~7M events/day
   (5 consumers × ~100 calls/sec × 86400 s × 500 bytes ≈ 6.5 M records
   ≈ 3.5 GB/day)

`T004b` was removed (Loki PVC sizing is an infrastructure-repo
concern — see the line in `tasks.md`). The test HERE is a procedural
audit, NOT a full PVC reconfiguration.

## T003 — Push path smoke test

The test payload is the exact shape the adapter emits. See
`packages/dk-data-client/python/dk_data_client/telemetry.py` for the
canonical schema.

```bash
NOW_NS=$(date +%s%N)
curl -sS -X POST "https://loki.behaviorlabs.ai/loki/api/v1/push" \
  -H "Content-Type: application/json" \
  --data @- <<EOF
{
  "streams": [
    {
      "stream": {
        "app": "adapter-telemetry",
        "client": "smoke-test",
        "method": "molecules.get",
        "outcome": "miss"
      },
      "values": [
        [
          "${NOW_NS}",
          "{\"ts\":$(date +%s),\"args_hash\":\"sha256:smoketest\",\"latency_ms\":42,\"cache_tier\":\"none\"}"
        ]
      ]
    }
  ]
}
EOF
```

Expected: HTTP 204 No Content. If you get 401, the cluster's Loki
gateway is expecting a bearer token — add `Authorization: Bearer $LOKI_PUSH_TOKEN`.

Wait 30 seconds, then query Grafana Explore:

```logql
{app="adapter-telemetry", client="smoke-test"} | json
```

One record should appear with `args_hash=sha256:smoketest`. If nothing
appears, check:

- **Loki gateway logs**: `kubectl -n loki logs -l app=loki-gateway --tail=100`
- **Distributor drop metric**: `loki_distributor_bytes_received_total` should
  increment
- **Ingester PVC fullness**: `kubelet_volume_stats_used_bytes{persistentvolumeclaim=~"loki.*"}`

## T004 — Retention + capacity audit

Run the T004c load driver against a staging Loki to confirm it can
absorb the Phase 2 peak:

```bash
export LOKI_PUSH_URL="https://loki-stage.behaviorlabs.ai/loki/api/v1/push"
python -m tests.load.loki_push --eps 500 --duration 600 --concurrency 20
```

Read the generated `docs/reports/loki-push-*.json`:

- **Pass**: `success_rate ≥ 0.99` AND `server_error_rate < 0.01`
- **Soft-fail (batching needed)**: `rate_limited_rate ≥ 0.05` —
  file a ticket to add ndjson batching to `dk-data-client v1.1`
- **Hard-fail**: `server_error_rate ≥ 0.01` — contact the infra team,
  do NOT ship adapter v0.1 yet

## T004 — Retention configuration (infra-repo side)

The Loki deployment lives in the shared infrastructure repo, not this
one. Capture the required configuration in a ticket filed to the
infra team:

- **Retention**: 30 days (hard delete after 30 d)
- **PVC size**: ≥ 200 GB (7× daily volume for headroom)
- **Ingester replicas**: ≥ 3 (AZ-spread)
- **Rate limits per tenant**: 10k events/sec burst, 5k sustained

Once the infra ticket is resolved, save the ticket URL + expected
go-live date in `docs/reports/T004-loki-capacity-ticket.md`.

## Related

- `tests/load/loki_push.py` — T004c driver
- `grafana/dashboards/dk-data-adapter-telemetry.json` — consumes this stream
- `packages/dk-data-client/python/dk_data_client/telemetry.py` — emitter
- `packages/dk-data-client/typescript/src/telemetry.ts` — emitter
