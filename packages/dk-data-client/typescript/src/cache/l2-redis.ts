/**
 * Redis-backed L2 cache.
 *
 * Uses `ioredis` as an optional peer dependency. If the consumer doesn't
 * install it, we throw at construction time with a clear hint rather
 * than a cryptic module-not-found stack trace.
 */

import type { L2Backend } from "./index.js";

// Declare a minimal shape so we can import the type without a hard dep.
interface IoRedisLike {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, mode: "EX", ttl: number): Promise<unknown>;
  quit(): Promise<unknown>;
}

type IoRedisCtor = new (url: string) => IoRedisLike;

export class RedisL2Cache implements L2Backend {
  private readonly client: IoRedisLike;

  constructor(url: string) {
    let IoRedis: IoRedisCtor;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      IoRedis = require("ioredis") as IoRedisCtor;
    } catch {
      throw new Error(
        "Redis cache backend requires the 'ioredis' peer dependency. " +
          "Install it with `pnpm add ioredis` or use the SQLite backend.",
      );
    }
    this.client = new IoRedis(url);
  }

  async get(key: string): Promise<unknown> {
    const raw = await this.client.get(key);
    if (raw === null) return null;
    try {
      return JSON.parse(raw) as unknown;
    } catch {
      return null;
    }
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    await this.client.set(key, JSON.stringify(value), "EX", ttlSeconds);
  }

  async close(): Promise<void> {
    await this.client.quit();
  }
}
