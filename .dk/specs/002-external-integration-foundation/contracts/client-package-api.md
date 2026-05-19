# Contract: Client Package Public API

## L2 cache TTL table (corrected per drift audit F-D019)

| Resource | L2 TTL | Rationale |
|---|---|---|
| Molecule identifiers / structural properties | 30 days | Immutable once assigned |
| Drug labels / regulatory status | 24 hours | FDA labels refresh daily at most |
| Clinical trials | 6 hours | CT.gov recruitment status changes mid-day |
| Adverse events / safety signals | 24 hours | Gold `safety_signals` rebuilds nightly at 22:00 UTC |
| Publications (PubMed, OpenAlex) | 24 hours | Source indexes refresh daily |
| Competitive landscape | **24 hours** (corrected from 6h) | Gold `competitive_landscape` rebuilds nightly; 6h caches the same miss 4× per day |
| Lifecycle stages | 24 hours | Same (gold nightly) |
| Molecule profile | 24 hours | Same (gold nightly) |
| Company pipeline | 24 hours | Same (gold nightly) |
| Resolution queue / pipeline status | never cache | Operational state, must be live |

Cache keys are content-addressed (`sha256(method:args)`); invalidation is TTL-only.

---


## TypeScript (`@datakinetic/dk-data-client`)

### Construction

```typescript
const client = new DkDataClient({
  meteringProxyUrl: string,     // e.g., https://data.behaviorlabs.ai
  apiKey: string,               // dk_data_{alias}_{suffix}
  fallbackMode?: "strict" | "upstream" | "hydrate",  // default: "upstream"
  cacheBackend?: "redis" | "sqlite",                  // default: redis
  cacheRedisUrl?: string,
  timeout?: number,             // default: 10_000 ms
});
```

### Molecule module

```typescript
client.molecules.resolve(nameOrId: string, options?: ResolveOptions): Promise<MoleculeRef>
client.molecules.search(query: string, options?: SearchOptions): Promise<Molecule[]>
client.molecules.get(id: string): Promise<Molecule>
client.molecules.getProfile(id: string): Promise<MoleculeProfile>
client.molecules.getSafety(id: string): Promise<SafetyProfile>
client.molecules.getAdverseEvents(id: string, options?: AEOptions): Promise<AdverseEvent[]>
client.molecules.getClinicalTrials(id: string, options?: TrialOptions): Promise<ClinicalTrial[]>
client.molecules.getDrugLabels(id: string): Promise<DrugLabel[]>
client.molecules.getBoxedWarnings(id: string): Promise<BoxedWarning[]>
client.molecules.getContraindications(id: string): Promise<Contraindication[]>
client.molecules.getCompetitiveLandscape(indication: string): Promise<CompetitiveLandscape>
client.molecules.getResolutionQueue(options?: QueueOptions): Promise<ResolutionQueueItem[]>
```

### Company / Condition / Publication / Patent / Provider modules

```typescript
client.companies.resolve(name: string): Promise<CompanyRef>
client.companies.get(id: string): Promise<Company>
client.companies.getPipeline(id: string): Promise<CompanyPipeline>

client.conditions.resolve(nameOrCode: string): Promise<ConditionRef>
client.conditions.search(query: string): Promise<Condition[]>

client.publications.search(query: string, options?: PubOptions): Promise<Publication[]>
client.publications.getByMolecule(moleculeId: string): Promise<Publication[]>
client.publications.getPubMed(pmid: string): Promise<Publication>
client.publications.getOpenAlex(workId: string): Promise<Publication>

client.patents.search(options?: PatentOptions): Promise<Patent[]>
client.patents.getByMolecule(moleculeId: string): Promise<Patent[]>

client.providers.resolve(npiOrName: string): Promise<ProviderRef>
client.providers.get(id: string): Promise<Provider>
```

### Catalog / health

```typescript
client.health(): Promise<HealthStatus>
client.catalog(): Promise<DataCatalog>
client.dataSources(): Promise<DataSource[]>
client.serverInfo(): Promise<{version: string, schema_fingerprint: string}>
```

### Telemetry opt-out (for tests)

```typescript
client.setTelemetryEnabled(enabled: boolean): void
```

### Typed errors (all methods may throw)

```typescript
class DkDataError extends Error {}
class DkDataAuthError extends DkDataError {}
class DkDataForbiddenError extends DkDataError {}
class DkDataNotFoundError extends DkDataError {}
class DkDataStaleError extends DkDataError { lastRefreshedAt: Date }
class DkDataUpstreamError extends DkDataError { upstream: string }
class DkDataRateLimitError extends DkDataError { retryAfter: number }
class DkDataServerError extends DkDataError { statusCode: number }
```

---

## Python (`dk-data-client`)

### Construction

```python
from dk_data_client import DkDataClient

client = DkDataClient(
    metering_proxy_url="https://data.behaviorlabs.ai",
    api_key="dk_data_tp_...",
    fallback_mode="strict",     # default "upstream"
    cache_backend="sqlite",     # default "redis"
    cache_redis_url=None,
    timeout=10.0,
)
```

### Async API (mirrors TS module structure)

```python
await client.molecules.resolve("durvalumab")
await client.molecules.search("pd-l1 inhibitor", threshold=0.3)
await client.molecules.get(molecule_id)
await client.molecules.get_profile(molecule_id)
await client.molecules.get_safety(molecule_id)
await client.molecules.get_adverse_events(molecule_id)
await client.molecules.get_clinical_trials(molecule_id)
await client.molecules.get_drug_labels(molecule_id)
await client.molecules.get_boxed_warnings(molecule_id)
await client.molecules.get_contraindications(molecule_id)

await client.companies.resolve("Pfizer")
await client.conditions.resolve("type 2 diabetes")
await client.publications.search(query)
await client.patents.search(options)
await client.providers.resolve(npi_or_name)

await client.health()
await client.catalog()
```

### Typed errors

```python
class DkDataError(Exception): ...
class DkDataAuthError(DkDataError): ...
class DkDataForbiddenError(DkDataError): ...
class DkDataNotFoundError(DkDataError): ...
class DkDataStaleError(DkDataError):
    last_refreshed_at: datetime
class DkDataUpstreamError(DkDataError):
    upstream: str
class DkDataRateLimitError(DkDataError):
    retry_after: float
class DkDataServerError(DkDataError):
    status_code: int
```

### Sync facade (for scripts and sync-only consumers)

```python
from dk_data_client.sync import DkDataClient  # sync shim over async client
client = DkDataClient(...)
result = client.molecules.resolve("durvalumab")  # blocking
```

---

## Telemetry event schema (emitted to Loki)

```json
{
  "ts": 1712937600,
  "client": "behavior-labs-ai",
  "client_version": "0.1.0",
  "method": "molecules.getProfile",
  "args_hash": "sha256:...",
  "outcome": "hit | miss | stale | fallthrough_upstream | fallthrough_hydrate | error",
  "error_type": "DkDataNotFoundError | null",
  "latency_ms": 124,
  "dk_data_version": "v0.42.1",
  "cache_tier": "l1 | l2 | none"
}
```

**Invariants**:
- No tokens, API keys, or response body content
- No PII/PHI
- One event per call (v0.1; batching deferred to v1.1)
