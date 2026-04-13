import { describe, it, expect } from "vitest";
import {
  TwoTierCache,
  makeKey,
  ttlFor,
  NEVER_CACHE,
  L2_TTL_SECONDS,
} from "../../src/cache/index.js";
import { L1Cache } from "../../src/cache/l1.js";

describe("makeKey", () => {
  it("is deterministic", () => {
    expect(makeKey("molecules.get", { id: "X" })).toBe(
      makeKey("molecules.get", { id: "X" }),
    );
  });

  it("differs for different args", () => {
    expect(makeKey("molecules.get", { id: "A" })).not.toBe(
      makeKey("molecules.get", { id: "B" }),
    );
  });

  it("normalizes argument order", () => {
    expect(makeKey("foo", { a: 1, b: 2 })).toBe(makeKey("foo", { b: 2, a: 1 }));
  });

  it("prefixes with method name", () => {
    const k = makeKey("molecules.get", { id: "X" });
    expect(k.startsWith("molecules.get:")).toBe(true);
  });
});

describe("ttlFor", () => {
  it("returns 24h for gold-backed methods", () => {
    expect(ttlFor("molecules.getProfile")).toBe(24 * 3600);
    expect(ttlFor("molecules.getCompetitiveLandscape")).toBe(24 * 3600);
  });

  it("returns null for never-cache methods", () => {
    expect(ttlFor("molecules.getResolutionQueue")).toBeNull();
    expect(ttlFor("health")).toBeNull();
    expect(ttlFor("serverInfo")).toBeNull();
  });

  it("returns 1h default for unknown methods", () => {
    expect(ttlFor("unknown.method")).toBe(3600);
  });
});

describe("NEVER_CACHE", () => {
  it("includes the expected methods", () => {
    expect(NEVER_CACHE.has("molecules.getResolutionQueue")).toBe(true);
    expect(NEVER_CACHE.has("health")).toBe(true);
  });
});

describe("L2_TTL_SECONDS", () => {
  it("uses 24h for gold-backed resources (F-D019 corrected)", () => {
    expect(L2_TTL_SECONDS["molecules.getCompetitiveLandscape"]).toBe(24 * 3600);
  });
});

describe("L1Cache", () => {
  it("get returns undefined on miss", () => {
    const c = new L1Cache<string>({ maxSize: 4 });
    expect(c.get("nope")).toBeUndefined();
  });

  it("set then get round-trip", () => {
    const c = new L1Cache<string>({ maxSize: 4 });
    c.set("k", "v");
    expect(c.get("k")).toBe("v");
  });

  it("evicts oldest when at capacity", () => {
    const c = new L1Cache<number>({ maxSize: 2 });
    c.set("a", 1);
    c.set("b", 2);
    c.set("c", 3);
    expect(c.get("a")).toBeUndefined();
    expect(c.get("b")).toBe(2);
    expect(c.get("c")).toBe(3);
  });

  it("expires entries after TTL", async () => {
    const c = new L1Cache<string>({ maxSize: 4, ttlMs: 10 });
    c.set("k", "v");
    await new Promise((r) => setTimeout(r, 20));
    expect(c.get("k")).toBeUndefined();
  });
});

describe("TwoTierCache", () => {
  it("miss then set then L1 hit", async () => {
    const cache = new TwoTierCache();
    expect(await cache.get("molecules.get", { id: "X" })).toBeNull();
    await cache.set("molecules.get", { id: "X" }, { name: "aspirin" });
    const hit = await cache.get<Record<string, unknown>>("molecules.get", { id: "X" });
    expect(hit).not.toBeNull();
    expect(hit!.tier).toBe("l1");
    expect(hit!.value).toEqual({ name: "aspirin" });
  });

  it("never-cache methods return null and ignore writes", async () => {
    const cache = new TwoTierCache();
    await cache.set("health", {}, { ok: true });
    expect(await cache.get("health", {})).toBeNull();
  });
});
