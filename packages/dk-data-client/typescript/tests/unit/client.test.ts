import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { DkDataClient } from "../../src/client.js";
import {
  DkDataAuthError,
  DkDataForbiddenError,
  DkDataNotFoundError,
  DkDataRateLimitError,
  DkDataServerError,
  DkDataStaleError,
} from "../../src/errors.js";

// Minimal `fetch` mock utility. Each test defines the next response —
// either a single response via `nextResponse` or a sequence via
// `responseQueue` (used by retry tests where consecutive calls need
// different responses).
let nextResponse: Response | Error | null = null;
let responseQueue: Array<Response | Error> = [];
let fetchCallCount = 0;
let sleepCalls: number[] = [];
const originalFetch = globalThis.fetch;
const originalSetTimeout = globalThis.setTimeout;

beforeEach(() => {
  nextResponse = null;
  responseQueue = [];
  fetchCallCount = 0;
  sleepCalls = [];
  // @ts-expect-error -- override global fetch for tests
  globalThis.fetch = vi.fn(async () => {
    fetchCallCount++;
    if (responseQueue.length > 0) {
      const head = responseQueue.shift();
      if (head instanceof Error) throw head;
      return head as Response;
    }
    if (nextResponse === null) {
      throw new Error("nextResponse not set");
    }
    if (nextResponse instanceof Error) {
      throw nextResponse;
    }
    return nextResponse;
  });
  // Stub setTimeout so retry-backoffs (and AbortController per-request
  // timers) never actually wait — every test must run in well under
  // the vitest default 5s ceiling, including the cap-at-5s retry case.
  // The callback is fired immediately so abort timers that "should"
  // fire still call abort(), but in practice fetch is also stubbed so
  // those callbacks see an already-resolved request.
  // @ts-expect-error -- stub setTimeout for tests
  globalThis.setTimeout = (fn: () => void, ms: number) => {
    sleepCalls.push(ms);
    fn();
    return 0 as unknown as ReturnType<typeof setTimeout>;
  };
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.setTimeout = originalSetTimeout;
});

function mockResponse(
  status: number,
  body: unknown = null,
  headers: Record<string, string> = {},
): Response {
  return new Response(body !== null ? JSON.stringify(body) : null, {
    status,
    headers: {
      "content-type": "application/json",
      ...headers,
    },
  });
}

function makeClient(fallbackMode: "strict" | "upstream" = "strict"): DkDataClient {
  const client = new DkDataClient({
    meteringProxyUrl: "http://test.local",
    apiKey: "dk_data_test_123",
    fallbackMode,
    cacheBackend: "none",
  });
  client.setTelemetryEnabled(false);
  return client;
}

describe("construction", () => {
  it("requires meteringProxyUrl", () => {
    expect(
      () => new DkDataClient({ meteringProxyUrl: "", apiKey: "x", cacheBackend: "none" }),
    ).toThrow(/meteringProxyUrl/);
  });

  it("requires apiKey", () => {
    expect(
      () =>
        new DkDataClient({
          meteringProxyUrl: "http://x",
          apiKey: "",
          cacheBackend: "none",
        }),
    ).toThrow(/apiKey/);
  });
});

describe("HTTP status → error mapping", () => {
  it("401 → DkDataAuthError", async () => {
    nextResponse = mockResponse(401, { error: "missing JWT" });
    const client = makeClient();
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataAuthError);
    await client.close();
  });

  it("403 → DkDataForbiddenError", async () => {
    nextResponse = mockResponse(403);
    const client = makeClient();
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataForbiddenError);
    await client.close();
  });

  it("404 in strict mode → DkDataNotFoundError", async () => {
    nextResponse = mockResponse(404);
    const client = makeClient("strict");
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataNotFoundError);
    await client.close();
  });

  it("410 → DkDataStaleError with parsed timestamp", async () => {
    nextResponse = mockResponse(
      410,
      { error: "stale" },
      { "x-last-refreshed-at": "2026-04-01T00:00:00Z" },
    );
    const client = makeClient();
    try {
      await client.molecules.getProfile("X");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(DkDataStaleError);
      expect((e as DkDataStaleError).lastRefreshedAt.getUTCFullYear()).toBe(2026);
    }
    await client.close();
  });

  it("429 → DkDataRateLimitError with retryAfter", async () => {
    nextResponse = mockResponse(429, null, { "retry-after": "30" });
    const client = makeClient();
    try {
      await client.molecules.get("X");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(DkDataRateLimitError);
      expect((e as DkDataRateLimitError).retryAfter).toBe(30);
    }
    await client.close();
  });

  it("500 → DkDataServerError with statusCode", async () => {
    nextResponse = mockResponse(500);
    const client = makeClient();
    try {
      await client.molecules.get("X");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(DkDataServerError);
      expect((e as DkDataServerError).statusCode).toBe(500);
    }
    await client.close();
  });
});

describe("2xx happy path", () => {
  it("returns parsed JSON array", async () => {
    nextResponse = mockResponse(200, [{ molecule_id: "X" }]);
    const client = makeClient();
    const rows = await client.molecules.search("aspirin");
    expect(rows).toHaveLength(1);
    expect(rows[0]!.molecule_id).toBe("X");
    await client.close();
  });
});

// Issue #281: retry-with-backoff on 503/429/transport errors.
//
// setTimeout is stubbed at the file level (top beforeEach) so retry
// backoffs and AbortController timers fire immediately and tests stay
// well under the vitest 5s ceiling. `sleepCalls` accumulates every
// scheduled delay so we can assert on the retry schedule.
describe("retry-with-backoff (#281)", () => {
  // Each fetch() call schedules one AbortController timer at the
  // per-method timeout (e.g. molecules.get → 3000ms). Strip exactly
  // `numFetches` instances of `abortMs` from the captured sleep
  // record so what remains is the retry-backoff schedule.
  function retryDelays(abortMs: number, numFetches: number): number[] {
    const remaining = [...sleepCalls];
    for (let i = 0; i < numFetches; i++) {
      const idx = remaining.indexOf(abortMs);
      if (idx >= 0) remaining.splice(idx, 1);
    }
    return remaining;
  }

  // molecules.get → 3000ms abort timer per fetch, see METHOD_TIMEOUTS_MS.
  const GET_ABORT = 3000;

  it("200 on first try — no retry, no backoff sleep", async () => {
    nextResponse = mockResponse(200, [{ molecule_id: "X" }]);
    const client = makeClient();
    await client.molecules.get("X");
    expect(fetchCallCount).toBe(1);
    expect(retryDelays(GET_ABORT, 1)).toEqual([]);
    await client.close();
  });

  it("503 + Retry-After=1 retries once then returns 200", async () => {
    responseQueue = [
      mockResponse(503, null, { "retry-after": "1" }),
      mockResponse(200, [{ molecule_id: "X" }]),
    ];
    const client = makeClient();
    const result = (await client.molecules.get("X")) as { molecule_id: string };
    expect(result.molecule_id).toBe("X");
    expect(fetchCallCount).toBe(2);
    expect(retryDelays(GET_ABORT, 2)).toEqual([1000]);
    await client.close();
  });

  it("503 + Retry-After=10 caps the wait at 5s", async () => {
    responseQueue = [
      mockResponse(503, null, { "retry-after": "10" }),
      mockResponse(200, [{ molecule_id: "X" }]),
    ];
    const client = makeClient();
    await client.molecules.get("X");
    expect(retryDelays(GET_ABORT, 2)).toEqual([5000]);
    await client.close();
  });

  it("503 without Retry-After uses the default delay", async () => {
    responseQueue = [mockResponse(503), mockResponse(200, [{ molecule_id: "X" }])];
    const client = makeClient();
    await client.molecules.get("X");
    expect(retryDelays(GET_ABORT, 2)).toEqual([1000]);
    await client.close();
  });

  it("429 retries once, then surfaces DkDataRateLimitError if it persists", async () => {
    responseQueue = [
      mockResponse(429, null, { "retry-after": "2" }),
      mockResponse(429, null, { "retry-after": "2" }),
    ];
    const client = makeClient();
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataRateLimitError);
    expect(fetchCallCount).toBe(2);
    expect(retryDelays(GET_ABORT, 2)).toEqual([2000]);
    await client.close();
  });

  it("429 then 200 succeeds on retry", async () => {
    responseQueue = [
      mockResponse(429, null, { "retry-after": "1" }),
      mockResponse(200, [{ molecule_id: "X" }]),
    ];
    const client = makeClient();
    const result = (await client.molecules.get("X")) as { molecule_id: string };
    expect(result.molecule_id).toBe("X");
    expect(retryDelays(GET_ABORT, 2)).toEqual([1000]);
    await client.close();
  });

  it("transport error retried once then succeeds", async () => {
    responseQueue = [
      new TypeError("fetch failed"),
      mockResponse(200, [{ molecule_id: "X" }]),
    ];
    const client = makeClient();
    await client.molecules.get("X");
    expect(fetchCallCount).toBe(2);
    const delays = retryDelays(GET_ABORT, 2);
    expect(delays).toHaveLength(1);
    // Jittered backoff lands in [500, 1000).
    expect(delays[0]!).toBeGreaterThanOrEqual(500);
    expect(delays[0]!).toBeLessThan(1000);
    await client.close();
  });

  it("transport error twice raises DkDataServerError(status=0)", async () => {
    responseQueue = [new TypeError("fetch failed"), new TypeError("fetch failed")];
    const client = makeClient();
    try {
      await client.molecules.get("X");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(DkDataServerError);
      expect((e as DkDataServerError).statusCode).toBe(0);
    }
    expect(fetchCallCount).toBe(2);
    await client.close();
  });

  it("401 is not retried", async () => {
    nextResponse = mockResponse(401);
    const client = makeClient();
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataAuthError);
    expect(fetchCallCount).toBe(1);
    expect(retryDelays(GET_ABORT, 1)).toEqual([]);
    await client.close();
  });

  it("403 is not retried", async () => {
    nextResponse = mockResponse(403);
    const client = makeClient();
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataForbiddenError);
    expect(fetchCallCount).toBe(1);
    await client.close();
  });

  it("404 is not retried", async () => {
    nextResponse = mockResponse(404);
    const client = makeClient("strict");
    await expect(client.molecules.get("X")).rejects.toBeInstanceOf(DkDataNotFoundError);
    expect(fetchCallCount).toBe(1);
    await client.close();
  });

  it("410 is not retried", async () => {
    nextResponse = mockResponse(
      410,
      { error: "stale" },
      { "x-last-refreshed-at": "2026-04-01T00:00:00Z" },
    );
    const client = makeClient();
    await expect(client.molecules.getProfile("X")).rejects.toBeInstanceOf(DkDataStaleError);
    expect(fetchCallCount).toBe(1);
    await client.close();
  });

  it("500 is not retried (only 503 among 5xx triggers a retry)", async () => {
    nextResponse = mockResponse(500);
    const client = makeClient();
    try {
      await client.molecules.get("X");
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(DkDataServerError);
      expect((e as DkDataServerError).statusCode).toBe(500);
    }
    expect(fetchCallCount).toBe(1);
    await client.close();
  });
});
