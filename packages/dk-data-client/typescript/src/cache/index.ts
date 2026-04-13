/**
 * Two-tier cache coordinator for dk-data-client.
 *
 * L1 = in-process LRU (see ./l1.ts)
 * L2 = Redis or SQLite (see ./l2-redis.ts, ./l2-sqlite.ts)
 *
 * Cache keys are content-addressed: `sha256(method:args)`.
 * TTLs come from the L2 TTL table — see client-package-api.md.
 *
 * Invariants:
 *   - L1 populates on L2 hit (so repeat reads hit L1 next time)
 *   - Writes go to BOTH tiers with method-specific L2 TTL
 *   - Methods in NEVER_CACHE bypass both tiers in both directions
 */

import { createHash } from "node:crypto";
import { L1Cache } from "./l1.js";

export type CacheTier = "l1" | "l2" | "none";

export interface CacheHit<T> {
  value: T;
  tier: CacheTier;
}

/** L2 backend interface. Implementations: Redis, SQLite. */
export interface L2Backend {
  get(key: string): Promise<unknown>;
  set(key: string, value: unknown, ttlSeconds: number): Promise<void>;
  close(): Promise<void>;
}

// -----------------------------------------------------------------------------
// TTL table — see contracts/client-package-api.md (corrected per F-D019).
// -----------------------------------------------------------------------------

const L2_TTL_SECONDS: Record<string, number> = {
  // Gold-backed, nightly rebuild
  "molecules.getProfile": 24 * 3600,
  "molecules.getCompetitiveLandscape": 24 * 3600,
  "molecules.getSafety": 24 * 3600,
  "companies.getPipeline": 24 * 3600,
  // Silver-backed lifecycle/identifier
  "molecules.get": 30 * 24 * 3600,
  "molecules.resolve": 30 * 24 * 3600,
  "companies.resolve": 30 * 24 * 3600,
  "conditions.resolve": 30 * 24 * 3600,
  "providers.resolve": 30 * 24 * 3600,
  // Drug labels
  "molecules.getDrugLabels": 24 * 3600,
  "molecules.getBoxedWarnings": 24 * 3600,
  "molecules.getContraindications": 24 * 3600,
  // Trials
  "molecules.getClinicalTrials": 6 * 3600,
  // AE
  "molecules.getAdverseEvents": 24 * 3600,
  // Publications
  "publications.search": 24 * 3600,
  "publications.getByMolecule": 24 * 3600,
  "publications.getPubMed": 24 * 3600,
  "publications.getOpenAlex": 24 * 3600,
  // Patents
  "patents.search": 7 * 24 * 3600,
  "patents.getByMolecule": 7 * 24 * 3600,
};

const NEVER_CACHE: ReadonlySet<string> = new Set([
  "molecules.getResolutionQueue",
  "health",
  "catalog",
  "dataSources",
  "serverInfo",
]);

function ttlFor(method: string): number | null {
  if (NEVER_CACHE.has(method)) return null;
  return L2_TTL_SECONDS[method] ?? 3600;
}

/** Canonicalize the args object so equivalent calls hash to the same key. */
function canonicalize(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return (
    "{" +
    keys.map((k) => JSON.stringify(k) + ":" + canonicalize(obj[k])).join(",") +
    "}"
  );
}

export function makeKey(method: string, args: Record<string, unknown>): string {
  const payload = JSON.stringify({ method, args: canonicalize(args) });
  const digest = createHash("sha256").update(payload).digest("hex");
  return `${method}:${digest}`;
}

// -----------------------------------------------------------------------------
// Two-tier coordinator
// -----------------------------------------------------------------------------

export interface TwoTierCacheOptions {
  l2?: L2Backend | null;
  l1MaxSize?: number;
  l1TtlMs?: number;
}

export class TwoTierCache {
  private readonly l1: L1Cache<unknown>;
  private readonly l2: L2Backend | null;

  constructor(opts: TwoTierCacheOptions = {}) {
    this.l1 = new L1Cache({
      maxSize: opts.l1MaxSize ?? 1024,
      ttlMs: opts.l1TtlMs ?? 5 * 60 * 1000,
    });
    this.l2 = opts.l2 ?? null;
  }

  async get<T>(
    method: string,
    args: Record<string, unknown>,
  ): Promise<CacheHit<T> | null> {
    if (NEVER_CACHE.has(method)) return null;
    const key = makeKey(method, args);
    const l1Hit = this.l1.get(key);
    if (l1Hit !== undefined) {
      return { value: l1Hit as T, tier: "l1" };
    }
    if (this.l2 !== null) {
      const l2Hit = await this.l2.get(key);
      if (l2Hit !== undefined && l2Hit !== null) {
        this.l1.set(key, l2Hit);
        return { value: l2Hit as T, tier: "l2" };
      }
    }
    return null;
  }

  async set(
    method: string,
    args: Record<string, unknown>,
    value: unknown,
  ): Promise<void> {
    if (NEVER_CACHE.has(method)) return;
    const key = makeKey(method, args);
    this.l1.set(key, value);
    if (this.l2 !== null) {
      const ttl = ttlFor(method);
      if (ttl !== null) {
        await this.l2.set(key, value, ttl);
      }
    }
  }

  async close(): Promise<void> {
    if (this.l2 !== null) {
      await this.l2.close();
    }
  }
}

export { L2_TTL_SECONDS, NEVER_CACHE, ttlFor };
