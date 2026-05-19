/**
 * Marker module for the upstream fallback mode.
 *
 * The actual upstream logic + shim registry lives in fallback/index.ts.
 * This file exists so T042 has a home for the documentation of the
 * upstream contract and the no-write-back invariant.
 *
 * **Upstream mode contract (v0.1)**:
 * - dk-data 404 triggers a shim call against the canonical upstream
 * - Shim response is transformed to match dk-data's shape and returned
 * - The result is NOT written back to dk-data (hydrate mode handles that in v1.1)
 * - Fallthrough is reported via telemetry with `outcome=fallthrough_upstream`
 *   and `extra.upstream = <shim.upstreamName>`
 *
 * **Shim registry**:
 *   molecules.resolve           -> pubchem
 *   molecules.get               -> pubchem
 *   molecules.getClinicalTrials -> clinicaltrials.gov
 *   publications.search         -> europe-pmc
 *
 * New shims register via `registerShim(method, shim)`.
 */

export { registerShim, fallbackToUpstream } from "./index.js";
export type { UpstreamShim, FallbackContext } from "./index.js";
