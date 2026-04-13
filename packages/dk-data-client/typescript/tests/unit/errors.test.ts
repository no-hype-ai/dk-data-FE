import { describe, it, expect } from "vitest";
import {
  DkDataError,
  DkDataAuthError,
  DkDataForbiddenError,
  DkDataNotFoundError,
  DkDataStaleError,
  DkDataUpstreamError,
  DkDataRateLimitError,
  DkDataServerError,
} from "../../src/errors.js";

describe("error hierarchy", () => {
  const cases = [
    new DkDataAuthError("x"),
    new DkDataForbiddenError("x"),
    new DkDataNotFoundError("x"),
    new DkDataStaleError("x", { lastRefreshedAt: new Date() }),
    new DkDataUpstreamError("x", { upstream: "pubchem" }),
    new DkDataRateLimitError("x", { retryAfter: 30 }),
    new DkDataServerError("x", { statusCode: 500 }),
  ];

  it.each(cases)("'%s' inherits DkDataError", (err) => {
    expect(err).toBeInstanceOf(DkDataError);
    expect(err).toBeInstanceOf(Error);
  });

  it("preserves message through inheritance", () => {
    const err = new DkDataAuthError("missing JWT");
    expect(err.message).toBe("missing JWT");
  });

  it("stale error carries lastRefreshedAt", () => {
    const ts = new Date("2026-04-01T00:00:00Z");
    const err = new DkDataStaleError("stale", { lastRefreshedAt: ts });
    expect(err.lastRefreshedAt).toEqual(ts);
  });

  it("upstream error carries upstream name", () => {
    const err = new DkDataUpstreamError("boom", { upstream: "pubchem" });
    expect(err.upstream).toBe("pubchem");
  });

  it("rate-limit error carries retryAfter", () => {
    const err = new DkDataRateLimitError("slow down", { retryAfter: 42 });
    expect(err.retryAfter).toBe(42);
  });

  it("server error carries statusCode", () => {
    const err = new DkDataServerError("boom", { statusCode: 503 });
    expect(err.statusCode).toBe(503);
  });

  it("details default to empty object", () => {
    const err = new DkDataError("no details");
    expect(err.details).toEqual({});
  });

  it("details are captured when provided", () => {
    const err = new DkDataNotFoundError("nope", { query: "X" });
    expect(err.details.query).toBe("X");
  });
});
