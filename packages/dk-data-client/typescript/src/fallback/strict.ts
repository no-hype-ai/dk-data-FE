/**
 * Marker module for the strict fallback mode.
 *
 * The actual strict-mode logic is a one-line branch in fallback/index.ts:
 * `if (mode === "strict") throw new DkDataNotFoundError(...)`. This file
 * exists so the task list (T041) has a concrete home for the
 * documentation of WHEN to use strict mode, not because strict needs a
 * class of its own.
 *
 * **Use strict when**:
 * - Human-facing UI where showing "no data" is better than stale/wrong
 * - Research-quality tooling that must cite dk-data, not upstream
 * - Tests that need determinism (no silent fallthrough to real APIs)
 *
 * **Do NOT use strict when**:
 * - Consumer pages want graceful degradation
 * - Batch pipelines can tolerate upstream latency
 */

export type { FallbackMode } from "./index.js";
