/**
 * Hydrate fallback mode — v1.1 stub.
 *
 * Feature: 002-external-integration-foundation (T145, US-1)
 *
 * See `dk_data_client/fallback_hydrate.py` for the design notes. The
 * TypeScript stub mirrors the Python stub so the TS + Py packages
 * remain symmetric — when v1.1 implements hydrate, both languages
 * ship the feature together.
 *
 * Currently the only public surface is a hook that throws with a
 * clear error pointing at the Phase 4 requirement.
 */

import type { FallbackContext, UpstreamShim } from "./index.js";

export class HydrateWriteBackClient {
  public readonly baseUrl: string;
  public readonly apiKey: string;

  constructor(baseUrl: string, apiKey: string) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  async writeBack(
    _ctx: FallbackContext,
    _upstreamValue: unknown,
  ): Promise<void> {
    throw new Error(
      "hydrate fallback mode is scheduled for @datakinetic/dk-data-client v1.1; " +
        "v0.1 raises before reaching write-back. See T145 and Phase 4 " +
        "idempotent ingestion endpoints.",
    );
  }
}

export async function hydrateFetchAndWriteBack(
  _shim: UpstreamShim,
  _writeBackClient: HydrateWriteBackClient,
): Promise<never> {
  throw new Error(
    "hydrate fallback mode is scheduled for @datakinetic/dk-data-client v1.1",
  );
}
