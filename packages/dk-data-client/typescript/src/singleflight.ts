/**
 * Single-flight (thundering-herd) coalescing for dk-data-client.
 *
 * Mirrors dk_data_client/singleflight.py exactly — see that file
 * for the full rationale. The TL;DR: N concurrent callers with the
 * same key share one in-flight invocation; the rest wait on the
 * same promise.
 *
 * Implementation uses a `Map<string, Promise<unknown>>` where the
 * first caller inserts the promise and subsequent callers await it.
 * On resolution (or rejection), the entry is removed so the next
 * attempt starts fresh.
 */

export class SingleFlight {
  private readonly pending: Map<string, Promise<unknown>> = new Map();

  async do<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const existing = this.pending.get(key);
    if (existing !== undefined) {
      // Another caller is already in flight for this key.
      return (await existing) as T;
    }

    // First caller — start the work and register it.
    const promise = fn().finally(() => {
      // Clean up regardless of success/failure so the next caller
      // starts a fresh attempt.
      this.pending.delete(key);
    });
    this.pending.set(key, promise);
    return promise;
  }

  activeCount(): number {
    return this.pending.size;
  }
}
