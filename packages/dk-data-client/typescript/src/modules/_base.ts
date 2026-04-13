/**
 * Base class for every domain module.
 *
 * Domain modules delegate transport, cache, and telemetry to the
 * underlying `DkDataClient`. They only know how to translate a
 * high-level method call into a PostgREST/FastAPI URL + params.
 */

import type { DkDataClient, CallOptions } from "../client.js";

export abstract class ModuleBase {
  constructor(protected readonly client: DkDataClient) {}

  protected async call(opts: CallOptions): Promise<unknown> {
    return this.client.call(opts);
  }
}
