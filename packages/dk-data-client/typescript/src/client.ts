/**
 * Core DkDataClient — binds transport, cache, fallback, and telemetry.
 *
 * Mirrors the Python client exactly. Every public call produces exactly
 * one telemetry event with a well-defined `outcome`, regardless of
 * whether the result came from L1, L2, the server, or an upstream
 * fallback.
 */

import { TwoTierCache, type CacheTier, type L2Backend } from "./cache/index.js";
import {
  DkDataAuthError,
  DkDataError,
  DkDataForbiddenError,
  DkDataNotFoundError,
  DkDataRateLimitError,
  DkDataServerError,
  DkDataStaleError,
  DkDataUpstreamError,
} from "./errors.js";
import { fallbackToUpstream, type FallbackMode } from "./fallback/index.js";
import { TelemetryEmitter, type Outcome } from "./telemetry.js";
import { MoleculesModule } from "./modules/molecules.js";
import { CompaniesModule } from "./modules/companies.js";
import { ConditionsModule } from "./modules/conditions.js";
import { PublicationsModule } from "./modules/publications.js";
import { PatentsModule } from "./modules/patents.js";
import { ProvidersModule } from "./modules/providers.js";

export interface DkDataClientConfig {
  meteringProxyUrl: string;
  apiKey: string;
  fallbackMode?: FallbackMode;
  cacheBackend?: "redis" | "sqlite" | "none";
  cacheRedisUrl?: string;
  cacheSqlitePath?: string;
  timeoutMs?: number;
  clientName?: string;
  clientVersion?: string;
  lokiPushUrl?: string;
  l2Backend?: L2Backend; // advanced: inject your own
}

export interface CallOptions {
  method: string;
  path: string;
  args?: Record<string, unknown>;
  params?: Record<string, string | number | boolean | undefined>;
  httpMethod?: string;
  jsonBody?: Record<string, unknown>;
}

export class DkDataClient {
  public readonly molecules: MoleculesModule;
  public readonly companies: CompaniesModule;
  public readonly conditions: ConditionsModule;
  public readonly publications: PublicationsModule;
  public readonly patents: PatentsModule;
  public readonly providers: ProvidersModule;

  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly timeoutMs: number;
  private readonly fallbackMode: FallbackMode;
  private readonly cache: TwoTierCache;
  private readonly telemetry: TelemetryEmitter;

  constructor(config: DkDataClientConfig) {
    if (!config.meteringProxyUrl) {
      throw new Error("meteringProxyUrl is required");
    }
    if (!config.apiKey) {
      throw new Error("apiKey is required");
    }
    this.baseUrl = config.meteringProxyUrl.replace(/\/+$/, "");
    this.apiKey = config.apiKey;
    this.timeoutMs = config.timeoutMs ?? 10_000;
    this.fallbackMode = config.fallbackMode ?? "upstream";

    // Build L2 backend lazily — only instantiate if the caller asked for one.
    let l2: L2Backend | null = config.l2Backend ?? null;
    if (l2 === null && config.cacheBackend === "redis") {
      if (!config.cacheRedisUrl) {
        throw new Error('cacheBackend="redis" requires cacheRedisUrl');
      }
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { RedisL2Cache } = require("./cache/l2-redis.js") as {
        RedisL2Cache: new (url: string) => L2Backend;
      };
      l2 = new RedisL2Cache(config.cacheRedisUrl);
    } else if (l2 === null && config.cacheBackend === "sqlite") {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { SqliteL2Cache } = require("./cache/l2-sqlite.js") as {
        SqliteL2Cache: new (path: string) => L2Backend;
      };
      l2 = new SqliteL2Cache(config.cacheSqlitePath ?? ".dk-data-client.sqlite");
    }

    this.cache = new TwoTierCache({ l2 });

    this.telemetry = new TelemetryEmitter({
      clientName: config.clientName ?? "unknown",
      clientVersion: config.clientVersion ?? "0.1.0",
      lokiPushUrl: config.lokiPushUrl,
    });

    this.molecules = new MoleculesModule(this);
    this.companies = new CompaniesModule(this);
    this.conditions = new ConditionsModule(this);
    this.publications = new PublicationsModule(this);
    this.patents = new PatentsModule(this);
    this.providers = new ProvidersModule(this);
  }

  async health(): Promise<unknown> {
    return this.rawGet("/health", "health");
  }

  async catalog(): Promise<unknown> {
    return this.rawGet("/catalog", "catalog");
  }

  async dataSources(): Promise<unknown> {
    return this.rawGet("/data_sources", "dataSources");
  }

  async serverInfo(): Promise<{ version: string; schema_fingerprint: string }> {
    const info = (await this.rawGet("/rpc/server_info", "serverInfo")) as
      | { version?: string; schema_fingerprint?: string }
      | null;
    if (info && typeof info === "object") {
      this.telemetry.setDkDataVersion(info.version ?? "");
      return {
        version: info.version ?? "",
        schema_fingerprint: info.schema_fingerprint ?? "",
      };
    }
    return { version: "", schema_fingerprint: "" };
  }

  async call(opts: CallOptions): Promise<unknown> {
    const args = opts.args ?? {};
    const started = performance.now();

    // Cache lookup
    const cacheHit = await this.cache.get<unknown>(opts.method, args);
    if (cacheHit !== null) {
      this.emit({
        method: opts.method,
        args,
        outcome: "hit",
        started,
        cacheTier: cacheHit.tier,
      });
      return cacheHit.value;
    }

    try {
      const value = await this.httpCall(opts);
      await this.cache.set(opts.method, args, value);
      this.emit({ method: opts.method, args, outcome: "miss", started });
      return value;
    } catch (e) {
      if (e instanceof DkDataStaleError) {
        this.emit({
          method: opts.method,
          args,
          outcome: "stale",
          started,
          errorType: "DkDataStaleError",
        });
        throw e;
      }
      if (e instanceof DkDataNotFoundError) {
        if (this.fallbackMode === "strict") {
          this.emit({
            method: opts.method,
            args,
            outcome: "error",
            started,
            errorType: "DkDataNotFoundError",
          });
          throw e;
        }
        try {
          const { value, upstreamName } = await fallbackToUpstream(
            opts.method,
            args,
            this.fallbackMode,
          );
          this.emit({
            method: opts.method,
            args,
            outcome: "fallthrough_upstream",
            started,
            extra: { upstream: upstreamName },
          });
          return value;
        } catch (inner) {
          if (inner instanceof DkDataUpstreamError) {
            this.emit({
              method: opts.method,
              args,
              outcome: "error",
              started,
              errorType: "DkDataUpstreamError",
            });
          } else {
            this.emit({
              method: opts.method,
              args,
              outcome: "error",
              started,
              errorType:
                inner instanceof Error ? inner.constructor.name : "Error",
            });
          }
          throw inner;
        }
      }
      this.emit({
        method: opts.method,
        args,
        outcome: "error",
        started,
        errorType: e instanceof Error ? e.constructor.name : "Error",
      });
      throw e;
    }
  }

  private async rawGet(path: string, method: string): Promise<unknown> {
    const started = performance.now();
    try {
      const value = await this.httpCall({
        method,
        path,
        httpMethod: "GET",
      });
      this.emit({ method, args: {}, outcome: "miss", started });
      return value;
    } catch (e) {
      this.emit({
        method,
        args: {},
        outcome: "error",
        started,
        errorType: e instanceof Error ? e.constructor.name : "Error",
      });
      throw e;
    }
  }

  private async httpCall(opts: CallOptions): Promise<unknown> {
    const url = new URL(opts.path, this.baseUrl + "/");
    for (const [k, v] of Object.entries(opts.params ?? {})) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await fetch(url.toString(), {
        method: opts.httpMethod ?? "GET",
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          Accept: "application/json",
          "User-Agent": `dk-data-client/0.1.0 (typescript)`,
          ...(opts.jsonBody ? { "Content-Type": "application/json" } : {}),
        },
        body: opts.jsonBody ? JSON.stringify(opts.jsonBody) : undefined,
        signal: controller.signal,
      });
    } catch (e) {
      clearTimeout(timer);
      throw new DkDataServerError(`transport error calling ${opts.path}: ${String(e)}`, {
        statusCode: 0,
      });
    }
    clearTimeout(timer);

    return this.handleResponse(response, opts.path);
  }

  private async handleResponse(response: Response, path: string): Promise<unknown> {
    const sc = response.status;
    if (sc >= 200 && sc < 300) {
      const ct = response.headers.get("content-type") ?? "";
      if (ct.startsWith("application/json")) {
        return (await response.json()) as unknown;
      }
      return await response.text();
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text().catch(() => "");
    }

    if (sc === 401) {
      throw new DkDataAuthError(`401 from ${path}`, { body });
    }
    if (sc === 403) {
      throw new DkDataForbiddenError(`403 from ${path}`, { body });
    }
    if (sc === 404) {
      throw new DkDataNotFoundError(`404 from ${path}`, { body });
    }
    if (sc === 410) {
      const last = response.headers.get("X-Last-Refreshed-At") ?? "";
      const lastRefreshedAt = last ? new Date(last) : new Date();
      throw new DkDataStaleError(`410 from ${path}`, { lastRefreshedAt, details: { body } });
    }
    if (sc === 429) {
      const retryAfter = Number(response.headers.get("Retry-After") ?? "1");
      throw new DkDataRateLimitError(`429 from ${path}`, {
        retryAfter: Number.isFinite(retryAfter) ? retryAfter : 1,
        details: { body },
      });
    }
    if (sc >= 500) {
      throw new DkDataServerError(`${sc} from ${path}`, { statusCode: sc, details: { body } });
    }
    throw new DkDataError(`unexpected status ${sc} from ${path}`, { body });
  }

  private emit(opts: {
    method: string;
    args: Record<string, unknown>;
    outcome: Outcome;
    started: number;
    cacheTier?: CacheTier;
    errorType?: string;
    extra?: Record<string, unknown>;
  }): void {
    const latencyMs = Math.floor(performance.now() - opts.started);
    this.telemetry.emit({
      method: opts.method,
      args: opts.args,
      outcome: opts.outcome,
      latencyMs,
      cacheTier: opts.cacheTier ?? "none",
      ...(opts.errorType ? { errorType: opts.errorType } : {}),
      ...(opts.extra ? { extra: opts.extra } : {}),
    });
  }

  setTelemetryEnabled(enabled: boolean): void {
    this.telemetry.setEnabled(enabled);
  }

  async close(): Promise<void> {
    await this.telemetry.close();
    await this.cache.close();
  }
}
