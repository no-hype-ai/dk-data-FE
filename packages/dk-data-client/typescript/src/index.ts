/**
 * @datakinetic/dk-data-client — first-party client for the dk-data platform.
 *
 * See `.dk/specs/002-external-integration-foundation/contracts/client-package-api.md`
 * for the canonical API contract. This package mirrors the Python package
 * exactly so consumers can switch languages without re-learning the surface.
 */

export { DkDataClient } from "./client.js";
export type { DkDataClientConfig } from "./client.js";
export {
  DkDataError,
  DkDataAuthError,
  DkDataForbiddenError,
  DkDataNotFoundError,
  DkDataStaleError,
  DkDataUpstreamError,
  DkDataRateLimitError,
  DkDataServerError,
} from "./errors.js";
export type { TelemetryEvent, Outcome, CacheTier } from "./telemetry.js";
export type { FallbackMode } from "./fallback/index.js";

export const VERSION = "0.1.0";
