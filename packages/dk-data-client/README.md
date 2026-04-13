# @datakinetic/dk-data-client

First-party client for the dk-data platform. Provides auth, two-tier
caching, fallback modes, and structured telemetry for every call.

This monorepo ships two language packages with the same API surface:

| Package | Path | Registry |
|---|---|---|
| TypeScript | `typescript/` | `@datakinetic/dk-data-client` (npm) |
| Python | `python/` | `dk-data-client` (PyPI) |

The canonical API contract lives at
`.dk/specs/002-external-integration-foundation/contracts/client-package-api.md`.

## Quick start

### TypeScript

```bash
pnpm add @datakinetic/dk-data-client
```

```ts
import { DkDataClient } from "@datakinetic/dk-data-client";

const client = new DkDataClient({
  meteringProxyUrl: "https://data.behaviorlabs.ai",
  apiKey: process.env.DK_DATA_API_KEY!,
});

const profile = await client.molecules.getProfile("CHEMBL25");
```

### Python

```bash
pip install dk-data-client
```

```python
from dk_data_client import DkDataClient

client = DkDataClient(
    metering_proxy_url="https://data.behaviorlabs.ai",
    api_key=os.environ["DK_DATA_API_KEY"],
)
profile = await client.molecules.get_profile("CHEMBL25")
```

See [`docs/consumer-onboarding.md`](../../docs/consumer-onboarding.md) for the
full step-by-step, including how to provision an API key.

## Directory layout

```
packages/dk-data-client/
├── typescript/          # @datakinetic/dk-data-client (npm)
│   ├── src/
│   │   ├── client.ts
│   │   ├── errors.ts
│   │   ├── telemetry.ts
│   │   ├── version.ts
│   │   ├── cache/
│   │   │   ├── index.ts       # two-tier coordinator
│   │   │   ├── l1.ts          # in-process LRU
│   │   │   ├── l2-redis.ts    # Redis backend (peer dep)
│   │   │   └── l2-sqlite.ts   # SQLite backend (peer dep, dev)
│   │   ├── fallback/
│   │   │   ├── index.ts       # strict / upstream / hydrate
│   │   │   ├── strict.ts
│   │   │   └── upstream.ts
│   │   └── modules/
│   │       ├── molecules.ts
│   │       ├── companies.ts
│   │       ├── conditions.ts
│   │       ├── publications.ts
│   │       ├── patents.ts
│   │       ├── providers.ts
│   │       └── catalog.ts
│   ├── tests/
│   │   ├── unit/              # vitest, no network
│   │   └── integration/       # against ephemeral dk-data
│   ├── package.json
│   └── tsconfig.json
│
├── python/              # dk-data-client (PyPI)
│   ├── dk_data_client/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── errors.py
│   │   ├── cache.py
│   │   ├── fallback.py
│   │   ├── telemetry.py
│   │   ├── sync.py             # sync facade over async client
│   │   └── modules/
│   │       ├── molecules.py
│   │       ├── companies.py
│   │       ├── conditions.py
│   │       ├── publications.py
│   │       ├── patents.py
│   │       └── providers.py
│   ├── tests/
│   │   ├── unit/               # pytest + respx, no network
│   │   └── integration/        # against ephemeral dk-data
│   └── pyproject.toml
│
├── scripts/
│   └── generate-types.sh       # OpenAPI → TS + Python types + fingerprint
│
├── tests/
│   ├── contract/
│   │   └── test_schema_fingerprint.py   # T064 — compares baked vs. live
│   └── integration/
│       ├── fixtures.py                  # ephemeral dk-data-FE stack
│       └── fixture.sql                  # minimum seed data
│
└── .github/workflows/
    ├── test.yml                # CI — typecheck, lint, unit, integration
    └── release.yml             # tag-triggered publish to npm + PyPI
```

## Development

### TypeScript

```bash
cd typescript/
pnpm install
pnpm run typecheck
pnpm run test
pnpm run build
```

### Python

```bash
cd python/
pip install -e ".[dev]"
pytest tests/unit/ -q
mypy dk_data_client
ruff check dk_data_client
```

### Integration tests

Both packages ship integration suites that spin an ephemeral dk-data-FE
stack via Docker Compose. Start the stack, set two env vars, run the
suite:

```bash
python tests/integration/fixtures.py up
# copy the printed base_url + api_key

DK_DATA_INTEGRATION_URL=http://localhost:3001 \
DK_DATA_INTEGRATION_KEY=dk_data_test_integration_key \
  pytest python/tests/integration/ -q

DK_DATA_INTEGRATION_URL=http://localhost:3001 \
DK_DATA_INTEGRATION_KEY=dk_data_test_integration_key \
  (cd typescript && pnpm run test tests/integration)

python tests/integration/fixtures.py down
```

The integration job in `.github/workflows/test.yml` is gated behind the
`integration` PR label so every PR doesn't pay the ~3-minute cost.

### Regenerating types after a dk-data contract change

```bash
DK_DATA_BASE_URL=https://data.behaviorlabs.ai \
DK_DATA_API_KEY=dk_data_... \
  ./scripts/generate-types.sh
```

Commit the refreshed `_fingerprint.py` + `version.ts`.

## Key invariants

- **Every call produces exactly one telemetry event.** No double-emitting,
  no silent failures.
- **Telemetry never blocks.** A broken Loki push is swallowed.
- **No raw arguments in telemetry.** Only `sha256(canonicalized args)`.
- **No tokens or response bodies in telemetry payloads.**
- **Cache keys are content-addressed.** `sha256(method:args)`, no
  normalization tricks.
- **L2 TTLs match the gold-table refresh cadence.** 24h for gold-backed
  resources (not 6h — see F-D019).
- **Strict mode NEVER falls through to upstream.** That's its one job.
- **Upstream mode NEVER writes back.** Hydrate mode ships in v1.1.

See `.dk/memory/principles.md` for the broader project principles.

## Related docs

- `docs/consumer-onboarding.md` — provisioning + integration walkthrough
- `docs/architecture.md` — auth flow, layered architecture
- `docs/data-catalog.md` — endpoint ↔ schema ↔ owner mapping
- `docs/runbooks/metering-proxy-401-debug.md` — auth failure triage
- `docs/runbooks/adapter-fallthrough-spike.md` — fallthrough alerting
