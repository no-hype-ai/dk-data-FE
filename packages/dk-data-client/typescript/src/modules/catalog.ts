/**
 * Catalog / health module — thin re-export for parity with the TS
 * contract. The underlying methods live on the `DkDataClient` itself
 * (`client.health()`, `client.catalog()`, `client.dataSources()`)
 * because they're cross-cutting, not per-domain.
 *
 * This file exists so T050 has a home, and so consumers doing
 * `import { CatalogModule } from '@datakinetic/dk-data-client/modules/catalog'`
 * get something that compiles.
 */

import type { DkDataClient } from "../client.js";

export class CatalogModule {
  constructor(private readonly client: DkDataClient) {}

  health(): Promise<unknown> {
    return this.client.health();
  }

  catalog(): Promise<unknown> {
    return this.client.catalog();
  }

  dataSources(): Promise<unknown> {
    return this.client.dataSources();
  }

  serverInfo(): Promise<{ version: string; schema_fingerprint: string }> {
    return this.client.serverInfo();
  }
}
