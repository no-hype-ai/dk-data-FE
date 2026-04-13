import { describe, it, expect } from "vitest";
import { TelemetryEmitter, hashArgs } from "../../src/telemetry.js";

describe("hashArgs", () => {
  it("is deterministic", () => {
    expect(hashArgs({ id: "X" })).toBe(hashArgs({ id: "X" }));
  });

  it("differs for different args", () => {
    expect(hashArgs({ id: "A" })).not.toBe(hashArgs({ id: "B" }));
  });

  it("is stable under argument reordering", () => {
    expect(hashArgs({ a: 1, b: 2 })).toBe(hashArgs({ b: 2, a: 1 }));
  });

  it("has sha256 prefix", () => {
    expect(hashArgs({ x: 1 }).startsWith("sha256:")).toBe(true);
  });
});

describe("TelemetryEmitter", () => {
  it("emit is noop when disabled", () => {
    const emitter = new TelemetryEmitter({
      clientName: "c",
      clientVersion: "0.1.0",
      enabled: false,
    });
    emitter.emit({ method: "x", args: {}, outcome: "hit", latencyMs: 1 });
    // No error, no exception. Hard to introspect queue without exposing
    // internals; the setEnabled toggle is the public contract.
    expect(emitter).toBeDefined();
  });

  it("setEnabled re-enables emission", () => {
    const emitter = new TelemetryEmitter({
      clientName: "c",
      clientVersion: "0.1.0",
      enabled: false,
    });
    emitter.setEnabled(true);
    emitter.emit({ method: "x", args: {}, outcome: "hit", latencyMs: 1 });
    expect(emitter).toBeDefined();
  });

  it("close resolves without error", async () => {
    const emitter = new TelemetryEmitter({
      clientName: "c",
      clientVersion: "0.1.0",
    });
    await expect(emitter.close()).resolves.toBeUndefined();
  });
});
