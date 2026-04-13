import { describe, it, expect } from "vitest";
import { SingleFlight } from "../../src/singleflight.js";

describe("SingleFlight", () => {
  it("first call runs fn and returns result", async () => {
    const sf = new SingleFlight();
    let invocations = 0;
    const fn = async () => {
      invocations += 1;
      return "v1";
    };
    const result = await sf.do("k", fn);
    expect(result).toBe("v1");
    expect(invocations).toBe(1);
  });

  it("10 concurrent calls coalesce into one invocation", async () => {
    const sf = new SingleFlight();
    let invocations = 0;
    let resolveGate!: () => void;
    const gate = new Promise<void>((r) => (resolveGate = r));

    const fn = async () => {
      invocations += 1;
      await gate;
      return "shared";
    };

    const tasks = Array.from({ length: 10 }, () => sf.do("k", fn));
    // Let all callers arrive at the single-flight before releasing fn
    await new Promise((r) => setTimeout(r, 10));
    resolveGate();
    const results = await Promise.all(tasks);
    expect(invocations).toBe(1);
    expect(results.every((r) => r === "shared")).toBe(true);
  });

  it("different keys do not coalesce", async () => {
    const sf = new SingleFlight();
    let invocations = 0;
    const fn = async () => {
      invocations += 1;
      return "v";
    };
    await Promise.all([sf.do("a", fn), sf.do("b", fn), sf.do("c", fn)]);
    expect(invocations).toBe(3);
  });

  it("exception propagates to all waiters", async () => {
    const sf = new SingleFlight();
    let invocations = 0;
    let resolveGate!: () => void;
    const gate = new Promise<void>((r) => (resolveGate = r));

    const fn = async () => {
      invocations += 1;
      await gate;
      throw new Error("boom");
    };

    const tasks = Array.from({ length: 5 }, () =>
      sf.do("k", fn).catch((e: unknown) => (e as Error).message),
    );
    await new Promise((r) => setTimeout(r, 10));
    resolveGate();
    const results = await Promise.all(tasks);
    expect(invocations).toBe(1);
    expect(results.every((r) => r === "boom")).toBe(true);
  });

  it("cleanup after completion allows new call", async () => {
    const sf = new SingleFlight();
    let invocations = 0;
    const fn = async () => {
      invocations += 1;
      return "v";
    };
    await sf.do("k", fn);
    await sf.do("k", fn);
    await sf.do("k", fn);
    expect(invocations).toBe(3);
    expect(sf.activeCount()).toBe(0);
  });
});
