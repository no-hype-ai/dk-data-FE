# @datakinetic/dk-data-client

First-party TypeScript client for the dk-data platform. See the
[monorepo root README](../README.md) for the full contract.

## Install

```bash
pnpm add @datakinetic/dk-data-client

# Optional L2 cache backends (peer deps):
pnpm add ioredis          # for Redis L2
pnpm add better-sqlite3   # for SQLite L2 (dev)
```

## Usage

```ts
import { DkDataClient } from "@datakinetic/dk-data-client";

const client = new DkDataClient({
  meteringProxyUrl: "https://data.behaviorlabs.ai",
  apiKey: process.env.DK_DATA_API_KEY!,
  fallbackMode: "upstream",         // default
  cacheBackend: "redis",
  cacheRedisUrl: "redis://localhost:6379",
  clientName: "behavior-labs-ai",
});

try {
  const profile = await client.molecules.getProfile("CHEMBL25");
  console.log(profile);
} finally {
  await client.close();
}
```

## Error handling

Every HTTP failure is a typed error:

```ts
import {
  DkDataError,           // base — catch for "anything went wrong"
  DkDataAuthError,       // 401
  DkDataForbiddenError,  // 403
  DkDataNotFoundError,   // 404
  DkDataStaleError,      // 410 (has .lastRefreshedAt)
  DkDataRateLimitError,  // 429 (has .retryAfter)
  DkDataServerError,     // 5xx (has .statusCode)
  DkDataUpstreamError,   // fallback to upstream failed
} from "@datakinetic/dk-data-client";

try {
  const trials = await client.molecules.getClinicalTrials("CHEMBL25");
} catch (e) {
  if (e instanceof DkDataStaleError) {
    console.warn(`stale since ${e.lastRefreshedAt}`);
  } else if (e instanceof DkDataRateLimitError) {
    await sleep(e.retryAfter * 1000);
  } else {
    throw e;
  }
}
```

## Development

```bash
pnpm install
pnpm run typecheck
pnpm run test
pnpm run build
```

See the [monorepo README](../README.md) for integration-test setup.
