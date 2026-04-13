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

// Minimal `fetch` mock utility. Each test defines the next response.
let nextResponse: Response | Error | null = null;
const originalFetch = globalThis.fetch;

beforeEach(() => {
  nextResponse = null;
  // @ts-expect-error -- override global fetch for tests
  globalThis.fetch = vi.fn(async () => {
    if (nextResponse === null) {
      throw new Error("nextResponse not set");
    }
    if (nextResponse instanceof Error) {
      throw nextResponse;
    }
    return nextResponse;
  });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
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
