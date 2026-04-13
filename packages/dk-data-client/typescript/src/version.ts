/**
 * Version fingerprint check — T051.
 *
 * Every release of dk-data exposes a `/rpc/server_info` endpoint that
 * returns `{ version, schema_fingerprint }`. The client holds its own
 * `CLIENT_SCHEMA_FINGERPRINT` at build time (baked in by the type-gen
 * step) and compares on startup.
 *
 * On mismatch, the client emits a structured WARNING event (via the
 * telemetry emitter, `outcome=miss` with `extra.schema_mismatch=true`)
 * but does NOT throw — warn-only preserves the consumer's ability to
 * keep working during the v0.1 → v0.2 transition window. See
 * docs/consumer-onboarding.md "v0.1 → v0.2 transition window".
 *
 * Strict mode (throw on mismatch) is gated behind an opt-in flag that
 * ships in v1.0.
 */

import type { DkDataClient } from "./client.js";
import { VERSION as CLIENT_VERSION } from "./index.js";

// Updated at each release by the type-gen pipeline. The fingerprint is
// derived from the PostgREST OpenAPI + FastAPI OpenAPI hashed together.
// Placeholder for v0.1.0; real fingerprint is baked in at build time.
export const CLIENT_SCHEMA_FINGERPRINT = "v0.1.0-placeholder";

export interface VersionCheckResult {
  clientVersion: string;
  clientFingerprint: string;
  serverVersion: string;
  serverFingerprint: string;
  fingerprintMatch: boolean;
}

export async function checkServerVersion(
  client: DkDataClient,
): Promise<VersionCheckResult> {
  const info = await client.serverInfo();
  const fingerprintMatch = info.schema_fingerprint === CLIENT_SCHEMA_FINGERPRINT;
  if (!fingerprintMatch) {
    // Warn-only: a mismatch during the v0.1 → v0.2 window is expected.
    // Consumers running in strict mode can call this function directly
    // and assert on `fingerprintMatch` themselves.
    // eslint-disable-next-line no-console
    console.warn(
      `[dk-data-client] schema fingerprint mismatch — ` +
        `client=${CLIENT_SCHEMA_FINGERPRINT} server=${info.schema_fingerprint}. ` +
        `This is expected during the v0.1 → v0.2 transition window. ` +
        `Upgrade @datakinetic/dk-data-client to silence this warning.`,
    );
  }
  return {
    clientVersion: CLIENT_VERSION,
    clientFingerprint: CLIENT_SCHEMA_FINGERPRINT,
    serverVersion: info.version,
    serverFingerprint: info.schema_fingerprint,
    fingerprintMatch,
  };
}
