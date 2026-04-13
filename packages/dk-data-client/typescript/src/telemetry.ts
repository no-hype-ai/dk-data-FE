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
        const event = this.queue.shift();
        if (!event) break;
        await this.push(event);
      }
    } finally {
      this.flushing = false;
    }
  }

  private async push(event: TelemetryEvent): Promise<void> {
    if (!this.lokiPushUrl) {
      // No Loki configured — structured log only
      return;
    }
    try {
      await fetch(this.lokiPushUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(eventToLokiStream(event)),
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
