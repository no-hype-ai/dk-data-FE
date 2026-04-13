/**
 * L1 in-process LRU cache for dk-data-client.
 *
 * Small, fast, per-instance. A dedicated dependency-free LRU keeps the
 * install surface minimal (no `lru-cache` peer dep). Items expire after
 * their TTL; we use lazy eviction on read rather than a background timer.
 */

export interface L1Entry<T> {
  value: T;
  expiresAt: number;
}

export class L1Cache<T = unknown> {
  private readonly maxSize: number;
  private readonly ttlMs: number;
  private readonly map: Map<string, L1Entry<T>> = new Map();

  constructor(opts: { maxSize?: number; ttlMs?: number } = {}) {
    this.maxSize = opts.maxSize ?? 1024;
    this.ttlMs = opts.ttlMs ?? 5 * 60 * 1000;
  }

  get(key: string): T | undefined {
    const entry = this.map.get(key);
    if (!entry) return undefined;
    if (entry.expiresAt < Date.now()) {
      this.map.delete(key);
      return undefined;
    }
    // LRU: touch the entry by reinserting (Map preserves insertion order)
    this.map.delete(key);
    this.map.set(key, entry);
    return entry.value;
  }

  set(key: string, value: T): void {
    if (this.map.has(key)) {
      this.map.delete(key);
    } else if (this.map.size >= this.maxSize) {
      // Evict oldest
      const firstKey = this.map.keys().next().value;
      if (firstKey !== undefined) this.map.delete(firstKey);
    }
    this.map.set(key, { value, expiresAt: Date.now() + this.ttlMs });
  }

  has(key: string): boolean {
    return this.get(key) !== undefined;
  }

  delete(key: string): void {
    this.map.delete(key);
  }

  clear(): void {
    this.map.clear();
  }

  get size(): number {
    return this.map.size;
  }
}
