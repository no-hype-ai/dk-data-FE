/**
 * Structured telemetry emission for dk-data-client.
 *
 * Every client call emits exactly one event with:
 *   method, args_hash, outcome, latency_ms, cache_tier, client_version
 *
 * Events ship to Loki via an HTTP push endpoint. Push failures are
 * swallowed — telemetry is best-effort and must NEVER block calls.
 *
 * Invariants:
 *   - No tokens, API keys, or response body content
 *   - No raw arguments — only sha256 hash
 *   - No PII/PHI
 */

import { createHash } from "node:crypto";

export type Outcome =
  | "hit"
  | "miss"
  | "stale"
  | "fallthrough_upstream"
  | "fallthrough_hydrate"
  | "error";

export type CacheTier = "l1" | "l2" | "none";

export interface TelemetryEvent {
  ts: number;
  client: string;
  clientVersion: string;
  method: string;
  argsHash: string;
  outcome: Outcome;
  latencyMs: number;
  dkDataVersion: string;
  cacheTier: CacheTier;
  errorType?: string;
  extra?: Record<string, unknown>;
}

export interface TelemetryEmitterOptions {
  clientName: string;
  clientVersion: string;
  lokiPushUrl?: string;
  dkDataVersion?: string;
  enabled?: boolean;
  queueMaxSize?: number;
}

// Batching tunables. Same defaults as the Python client.
const BATCH_SIZE = 100;
const BATCH_WAIT_MS = 50;

/** sha256(canonicalized args) — NEVER log raw args themselves. */
export function hashArgs(args: Record<string, unknown>): string {
  const keys = Object.keys(args).sort();
  const canonical = JSON.stringify(
    keys.reduce<Record<string, unknown>>((acc, k) => {
      acc[k] = args[k];
      return acc;
    }, {}),
  );
  const digest = createHash("sha256").update(canonical).digest("hex").slice(0, 32);
  return `sha256:${digest}`;
}

function eventToLokiStream(event: TelemetryEvent): unknown {
  const labels = {
    app: "adapter-telemetry",
    client: event.client,
    method: event.method,
    outcome: event.outcome,
  };
  const linePayload: Record<string, unknown> = {
    ts: event.ts,
    client_version: event.clientVersion,
    args_hash: event.argsHash,
    latency_ms: event.latencyMs,
    cache_tier: event.cacheTier,
    dk_data_version: event.dkDataVersion,
  };
  if (event.errorType) linePayload.error_type = event.errorType;
  if (event.extra) linePayload.extra = event.extra;
  const nsTimestamp = (BigInt(event.ts) * 1_000_000_000n).toString();
  return {
    streams: [
      {
        stream: labels,
        values: [[nsTimestamp, JSON.stringify(linePayload)]],
      },
    ],
  };
}

export class TelemetryEmitter {
  private readonly clientName: string;
  private readonly clientVersion: string;
  private readonly lokiPushUrl: string | undefined;
  private dkDataVersion: string;
  private enabled: boolean;
  private readonly queueMaxSize: number;
  private queue: TelemetryEvent[] = [];
  private flushing = false;

  constructor(opts: TelemetryEmitterOptions) {
    this.clientName = opts.clientName;
    this.clientVersion = opts.clientVersion;
    this.lokiPushUrl = opts.lokiPushUrl;
    this.dkDataVersion = opts.dkDataVersion ?? "";
    this.enabled = opts.enabled ?? true;
    this.queueMaxSize = opts.queueMaxSize ?? 256;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  setDkDataVersion(version: string): void {
    this.dkDataVersion = version;
  }

  emit(opts: {
    method: string;
    args: Record<string, unknown>;
    outcome: Outcome;
    latencyMs: number;
    cacheTier?: CacheTier;
    errorType?: string;
    extra?: Record<string, unknown>;
  }): void {
    if (!this.enabled) return;
    const event: TelemetryEvent = {
      ts: Math.floor(Date.now() / 1000),
      client: this.clientName,
      clientVersion: this.clientVersion,
      method: opts.method,
      argsHash: hashArgs(opts.args),
      outcome: opts.outcome,
      latencyMs: opts.latencyMs,
      dkDataVersion: this.dkDataVersion,
      cacheTier: opts.cacheTier ?? "none",
      ...(opts.errorType ? { errorType: opts.errorType } : {}),
      ...(opts.extra ? { extra: opts.extra } : {}),
    };
    if (this.queue.length >= this.queueMaxSize) {
      // Drop oldest to bound memory
      this.queue.shift();
    }
    this.queue.push(event);
    if (!this.flushing) {
      // fire-and-forget
      void this.flush();
    }
  }

  private async flush(): Promise<void> {
    if (this.flushing) return;
    this.flushing = true;
    try {
      while (this.queue.length > 0) {
        // Batch up to BATCH_SIZE events into a single Loki POST.
        // This is a 100× reduction in push call rate vs. per-event
        // emission. The tradeoff: tail events of an idle burst may
        // wait up to `batchWaitMs` before being flushed.
        const batch = this.queue.splice(0, BATCH_SIZE);
        await this.pushBatch(batch);

        // If more events arrived while we were pushing, let the
        // event loop run briefly so producers can add a few more
        // before we drain the next batch. This keeps batches full
        // under steady load without penalizing latency in tests.
        if (this.queue.length > 0 && this.queue.length < BATCH_SIZE) {
          await new Promise((resolve) => setTimeout(resolve, BATCH_WAIT_MS));
        }
      }
    } finally {
      this.flushing = false;
    }
  }

  private async pushBatch(batch: TelemetryEvent[]): Promise<void> {
    if (batch.length === 0) return;
    if (!this.lokiPushUrl) {
      // No Loki configured — structured log only
      return;
    }

    // Merge events that share a label set (app/client/method/outcome)
    // into ONE Loki stream entry. This is Loki's preferred payload
    // shape and further reduces ingestion cost.
    const streamsByKey = new Map<
      string,
      { stream: Record<string, string>; values: Array<[string, string]> }
    >();
    for (const event of batch) {
      const rendered = eventToLokiStream(event) as {
        streams: Array<{
          stream: Record<string, string>;
          values: Array<[string, string]>;
        }>;
      };
      const stream = rendered.streams[0]!;
      const key = `${stream.stream.app}|${stream.stream.client}|${stream.stream.method}|${stream.stream.outcome}`;
      const existing = streamsByKey.get(key);
      if (existing) {
        existing.values.push(...stream.values);
      } else {
        streamsByKey.set(key, { stream: stream.stream, values: [...stream.values] });
      }
    }
    const payload = { streams: Array.from(streamsByKey.values()) };

    try {
      await fetch(this.lokiPushUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      // Swallow — telemetry is best-effort
    }
  }

  async close(): Promise<void> {
    // Drain any pending events with a short budget.
    const deadline = Date.now() + 1000;
    while (this.queue.length > 0 && Date.now() < deadline) {
      // eslint-disable-next-line no-await-in-loop
      await this.flush();
    }
  }
}
